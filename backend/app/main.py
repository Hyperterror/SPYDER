from contextlib import asynccontextmanager
import socket
import time
import uuid
from urllib.parse import urlparse
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import settings, validate_security_configuration
from app.core.database import Base, engine, ensure_late_columns, get_db
from app.core.logging import configure_structured_logging, request_id_ctx
from app.core.neo4j import get_neo4j, close_neo4j
from app.api import auth, cases, evidence, graph, audit, intelligence
from app.intelligence.leads import LeadRepository
import app.models  # noqa: F401 — registers all models with SQLAlchemy mapper

logger = configure_structured_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_security_configuration(settings)

    # Startup: create PostgreSQL tables in dev/test only (production relies on Alembic)
    if not settings.is_production:
        try:
            Base.metadata.create_all(bind=engine)
            added = ensure_late_columns(engine)
            for col in added:
                logger.info("Added missing column %s", col)
            logger.info("Database tables verified")
        except Exception as e:
            logger.warning("Database not reachable at startup: %s", e)

    # Startup: Neo4j constraints (best-effort)
    try:
        neo4j = get_neo4j()
        neo4j.verify_connectivity()
        neo4j.setup_constraints()
        logger.info("Neo4j connected")
    except Exception as e:
        logger.warning("Neo4j not reachable at startup: %s", e)

    # Startup: Intelligence Leads Pre-cache (best-effort)
    try:
        LeadRepository.get_instance().load_if_needed()
        logger.info("Phase 4 Intelligence Leads loaded into cache")
    except Exception as e:
        logger.warning("Intelligence leads could not be pre-loaded at startup: %s", e)

    yield

    # Shutdown
    close_neo4j()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="SPYDER-DETECT — Evidence-Centric Criminal Intelligence & Investigation API",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_correlation_middleware(request: Request, call_next) -> Response:
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_ctx.set(req_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        response.headers["X-Request-ID"] = req_id
        logger.info(
            "%s %s -> %s (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
    finally:
        request_id_ctx.reset(token)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(evidence.direct_router)
app.include_router(graph.router)
app.include_router(audit.router)
app.include_router(intelligence.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/live")
def health_live():
    return {"status": "alive", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    checks = {
        "database": {"status": "unknown"},
        "neo4j": {"status": "unknown", "optional": True},
        "storage": {"status": "unknown"},
        "queue": {"status": "unknown"},
    }
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
        checks["database"] = {"status": "up"}
    except Exception as exc:
        checks["database"] = {"status": "down", "detail": str(exc)[:120]}

    try:
        parsed_neo = urlparse(settings.NEO4J_URI.replace("bolt://", "http://").replace("neo4j://", "http://"))
        host = parsed_neo.hostname or "localhost"
        port = parsed_neo.port or 7687
        with socket.create_connection((host, port), timeout=0.5):
            pass
        neo4j = get_neo4j()
        neo4j.verify_connectivity()
        checks["neo4j"] = {"status": "up", "optional": True}
    except Exception as exc:
        checks["neo4j"] = {"status": "degraded", "optional": True, "detail": str(exc)[:120]}

    try:
        from app.services.storage import get_storage
        st = get_storage()
        checks["storage"] = {"status": "up", "backend": st.__class__.__name__}
    except Exception as exc:
        checks["storage"] = {"status": "down", "detail": str(exc)[:120]}

    if settings.CELERY_TASK_ALWAYS_EAGER:
        checks["queue"] = {"status": "eager_local"}
    else:
        try:
            import redis
            r = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=1.5)
            r.ping()
            checks["queue"] = {"status": "up"}
        except Exception as exc:
            checks["queue"] = {"status": "down", "detail": str(exc)[:120]}

    overall = "ready" if db_ok else "unavailable"
    status_code = 200 if db_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "checks": checks, "version": settings.APP_VERSION},
    )

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import Base, engine, ensure_late_columns
from app.core.neo4j import get_neo4j, close_neo4j
from app.api import auth, cases, evidence, graph, audit, intelligence
from app.intelligence.leads import LeadRepository
import app.models  # noqa: F401 — registers all models with SQLAlchemy mapper


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all PostgreSQL tables (best-effort — skips if DB is down)
    try:
        Base.metadata.create_all(bind=engine)
        added = ensure_late_columns(engine)
        for col in added:
            print(f"[OK] Added missing column {col}")
        print("[OK] Database tables verified")
    except Exception as e:
        print(f"[WARN] Database not reachable at startup — tables not created: {e}")

    # Startup: Neo4j constraints (best-effort)
    try:
        neo4j = get_neo4j()
        neo4j.verify_connectivity()
        neo4j.setup_constraints()
        print("[OK] Neo4j connected")
    except Exception as e:
        print(f"[WARN] Neo4j not reachable at startup: {e}")

    # Startup: Intelligence Leads Pre-cache (best-effort)
    try:
        LeadRepository.get_instance().load_if_needed()
        print("[OK] Phase 4 Intelligence Leads loaded into cache")
    except Exception as e:
        print(f"[WARN] Intelligence leads could not be pre-loaded at startup: {e}")

    yield

    # Shutdown
    close_neo4j()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="SPYDER-DETECT Phase 1 — EvidenceGraph Secure Criminal Intelligence API",
    lifespan=lifespan,
)

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
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}

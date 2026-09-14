from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import Base, engine
from app.core.neo4j import get_neo4j, close_neo4j
from app.api import auth, cases, evidence, graph, audit
import app.models  # noqa: F401 — registers all models with SQLAlchemy mapper


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all PostgreSQL tables (best-effort — skips if DB is down)
    try:
        Base.metadata.create_all(bind=engine)
        print("[OK] PostgreSQL tables verified")
    except Exception as e:
        print(f"[WARN] PostgreSQL not reachable at startup — tables not created: {e}")

    # Startup: Neo4j constraints (best-effort)
    try:
        neo4j = get_neo4j()
        neo4j.setup_constraints()
        neo4j.verify_connectivity()
        print("[OK] Neo4j connected")
    except Exception as e:
        print(f"[WARN] Neo4j not reachable at startup: {e}")

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
app.include_router(graph.router)
app.include_router(audit.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}

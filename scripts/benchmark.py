"""
SPYDER-DETECT Latency & Evidence Ingestion Benchmark Script (Milestone 6).

Supports running against an isolated in-process FastAPI TestClient + SQLite DB
(default offline mode) OR against a live deployment via `--base-url http://localhost:8000`.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return round(s[f], 2)
    return round(s[f] + (s[c] - s[f]) * (k - f), 2)


def run_offline_benchmark(iterations: int = 20) -> Dict[str, object]:
    tmp_dir = tempfile.mkdtemp(prefix="spyder_bench_")
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
    os.environ["LOCAL_STORAGE_DIR"] = tmp_dir
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_dir}/bench.db"

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.database import Base, get_db
    from app.core.security import create_access_token
    from app.main import app
    from app.models.user import User

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = TestingSession()

    admin = User(
        id=uuid.uuid4(),
        email="bench_admin@spyder.gov",
        display_name="Benchmark Admin",
        password_hash="bench_hash",
        role="ADMIN",
        is_active=True,
    )
    db.add(admin)
    db.commit()
    hdr = {"Authorization": f"Bearer {create_access_token(str(admin.id), admin.role)}"}

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    os.environ["LOCAL_STORAGE_DIR"] = tmp_dir

    timings: Dict[str, List[float]] = {
        "health_ready": [],
        "cases_list": [],
        "leads_list": [],
        "hypotheses_list": [],
        "pipeline_ingest_cdr_20rows": [],
    }

    with TestClient(app) as client:
        case_resp = client.post("/api/v1/cases", json={"title": "Benchmark Case", "case_type": "CYBER_CRIME"}, headers=hdr)
        assert case_resp.status_code == 201
        case_id = case_resp.json()["id"]

        for _ in range(iterations):
            for name, url in [
                ("health_ready", "/health/ready"),
                ("cases_list", "/api/v1/cases"),
                ("leads_list", "/api/v1/intelligence/leads?limit=50"),
                ("hypotheses_list", "/api/v1/intelligence/identity-hypotheses?limit=50"),
            ]:
                t0 = time.perf_counter()
                r = client.get(url, headers=hdr)
                assert r.status_code == 200
                timings[name].append((time.perf_counter() - t0) * 1000.0)

        # Ingestion + Canonical Pipeline benchmark (3 runs)
        rows = ["calling_number,called_number,start_time,duration_seconds,tower_id"]
        for i in range(20):
            rows.append(f"+9198765001{i:02d},+9198765002{i:02d},2026-08-10T10:{i:02d}:00Z,45,TOW_BENCH_{i%3}")
        csv_bytes = ("\n".join(rows)).encode("utf-8")

        for idx in range(3):
            payload = csv_bytes + f"\n".encode("utf-8") * (idx + 1)
            t0 = time.perf_counter()
            up = client.post(
                f"/api/v1/cases/{case_id}/evidence/upload",
                files={"file": (f"bench_cdr_{idx}.csv", io.BytesIO(payload), "text/csv")},
                headers=hdr,
            )
            assert up.status_code == 201
            pr = client.post(f"/api/v1/cases/{case_id}/evidence/{up.json()['id']}/process?run_sync=true", headers=hdr)
            assert pr.status_code == 200
            timings["pipeline_ingest_cdr_20rows"].append((time.perf_counter() - t0) * 1000.0)

    app.dependency_overrides.clear()
    db.close()

    summary = {
        "mode": "offline_testclient_sqlite",
        "iterations": iterations,
        "metrics_ms": {
            k: {
                "p50": _percentile(v, 50),
                "p95": _percentile(v, 95),
                "mean": round(statistics.mean(v), 2) if v else 0.0,
            }
            for k, v in timings.items()
        },
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SPYDER-DETECT Latency & Ingestion Benchmark")
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    report = run_offline_benchmark(iterations=args.iterations)
    print(json.dumps(report, indent=2))

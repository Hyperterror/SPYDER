"""Functional API tests for the public, versioned SPYDER-DETECT routes."""
from __future__ import annotations

import hashlib
import os
import sys
import types
import uuid
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


# Keep SQLite-compatible model types and prevent tests from using a developer DB.
os.environ["DATABASE_URL"] = "sqlite:///./spyder_test.db"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api import evidence as evidence_api
from app.api import intelligence as intelligence_api
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.intelligence.priority_models import PriorityListResponse
from app.main import app
from app.models.case import Case
from app.models.user import User
from app.services.ocr import extract_text_from_image_bytes, extract_text_from_pdf_bytes


class _MemoryStorage:
    bucket = "test-evidence"

    def upload(self, object_key: str, file_bytes: bytes, content_type: str) -> str:
        return object_key


@pytest.fixture()
def api_context(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[httpx.ASGITransport, str], None, None]:
    """Provide an isolated SQLite app, an administrator, and a case."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    db = session_factory()
    admin = User(
        id=uuid.uuid4(),
        email="api-test-admin@spyder.gov",
        password_hash=hash_password("ApiTest@1234"),
        display_name="API Test Admin",
        role="ADMIN",
        is_active=True,
    )
    case = Case(
        id=uuid.uuid4(),
        case_code="API-TEST-001",
        title="API integration test case",
        case_type="CYBER_CRIME",
        status="ACTIVE",
        created_by=admin.id,
    )
    db.add_all((admin, case))
    db.commit()
    case_id = str(case.id)
    db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(evidence_api, "get_storage", lambda: _MemoryStorage())
    monkeypatch.setattr(evidence_api, "upsert_document_node", lambda **_: {})

    try:
        yield httpx.ASGITransport(app=app), case_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


async def _login(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "api-test-admin@spyder.gov", "password": "ApiTest@1234"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_canonical_frontend_routes_are_registered() -> None:
    """Catch accidental prefix/signature drift before a frontend release."""
    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/cases/{case_id}/evidence/upload" in paths
    assert "/api/v1/cases/{case_id}/graph/subgraph" in paths
    assert "/api/v1/intelligence/priorities" in paths


@pytest.mark.asyncio
async def test_health_and_login_return_expected_payload(api_context: tuple[httpx.ASGITransport, str]) -> None:
    transport, _ = api_context
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "api-test-admin@spyder.gov", "password": "ApiTest@1234"},
        )
        assert login.status_code == 200
        assert login.json()["token_type"] == "bearer"
        assert login.json()["access_token"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content_type", "contents"),
    [
        ("calls.csv", "text/csv", b"calling_number,called_number\n9000000000,9111111111\n"),
        ("ledger.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"test workbook"),
        ("metadata.json", "application/json", b'{"source":"api-test"}'),
        ("searchable.pdf", "application/pdf", b"%PDF-test-content"),
        ("notice.png", "image/png", b"png-test-content"),
        ("notice.jpg", "image/jpeg", b"jpg-test-content"),
        ("notice.jpeg", "image/jpeg", b"jpeg-test-content"),
    ],
)
async def test_upload_accepts_supported_formats_and_returns_hash(
    api_context: tuple[httpx.ASGITransport, str],
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content_type: str,
    contents: bytes,
) -> None:
    transport, case_id = api_context
    extracted_pdf_text = "Searchable PDF text extracted for API integration verification."
    extracted_image_text = "Image text extracted for API integration verification."
    monkeypatch.setattr(evidence_api, "extract_text_from_pdf_bytes", lambda _: extracted_pdf_text)
    monkeypatch.setattr(evidence_api, "extract_text_from_image_bytes", lambda _: extracted_image_text)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        headers = await _login(client)
        response = await client.post(
            f"/api/v1/cases/{case_id}/evidence/upload",
            headers=headers,
            files={"file": (filename, contents, content_type)},
        )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["sha256_hash"] == hashlib.sha256(contents).hexdigest()
    if filename.endswith(".pdf"):
        assert payload["extracted_text"] == extracted_pdf_text
        assert payload["extracted_text_preview"] == extracted_pdf_text
    elif filename.endswith((".png", ".jpg", ".jpeg")):
        assert payload["extracted_text"] == extracted_image_text
        assert payload["extracted_text_preview"] == extracted_image_text
    else:
        assert payload["extracted_text"] is None
        assert payload["extracted_text_preview"] is None


@pytest.mark.asyncio
async def test_graph_subgraph_returns_cytoscape_collections(
    api_context: tuple[httpx.ASGITransport, str],
) -> None:
    transport, case_id = api_context
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            f"/api/v1/cases/{case_id}/graph/subgraph",
            headers=await _login(client),
        )

    assert response.status_code == 200, response.text
    assert isinstance(response.json()["nodes"], list)
    assert isinstance(response.json()["edges"], list)


@pytest.mark.asyncio
async def test_priority_endpoint_returns_priority_payload(
    api_context: tuple[httpx.ASGITransport, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    transport, _ = api_context

    class _PriorityEngine:
        def get_priorities(self, **_: object) -> PriorityListResponse:
            return PriorityListResponse(
                total=0, limit=50, offset=0, high_count=0,
                medium_count=0, low_count=0, priorities=[],
            )

    monkeypatch.setattr(
        intelligence_api.InvestigationPriorityEngine,
        "get_instance",
        lambda: _PriorityEngine(),
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/intelligence/priorities",
            headers=await _login(client),
        )

    assert response.status_code == 200, response.text
    assert response.json()["priorities"] == []


def test_pdf_service_prefers_sufficient_native_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Page:
        def extract_text(self) -> str:
            return "Native extraction " * 5

    pypdf = types.ModuleType("pypdf")
    pypdf.PdfReader = lambda _: types.SimpleNamespace(pages=[_Page()])
    monkeypatch.setitem(sys.modules, "pypdf", pypdf)

    assert extract_text_from_pdf_bytes(b"pdf bytes").startswith("Native extraction")


def test_pdf_service_uses_ocr_when_native_text_is_insufficient(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Page:
        def extract_text(self) -> str:
            return "short"

    pypdf = types.ModuleType("pypdf")
    pypdf.PdfReader = lambda _: types.SimpleNamespace(pages=[_Page()])
    pdf2image = types.ModuleType("pdf2image")
    pdf2image.convert_from_bytes = lambda _: ["page-one", "page-two"]
    pytesseract = types.ModuleType("pytesseract")
    pytesseract.image_to_string = lambda page: f"OCR {page}"
    monkeypatch.setitem(sys.modules, "pypdf", pypdf)
    monkeypatch.setitem(sys.modules, "pdf2image", pdf2image)
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract)

    assert extract_text_from_pdf_bytes(b"scanned pdf") == "OCR page-one\nOCR page-two"


def test_image_service_uses_pillow_and_tesseract(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Image:
        def __enter__(self) -> "_Image":
            return self

        def __exit__(self, *_: object) -> None:
            return None

    pil = types.ModuleType("PIL")
    pil_image = types.ModuleType("PIL.Image")
    pil_image.open = lambda _: _Image()
    pil.Image = pil_image
    pytesseract = types.ModuleType("pytesseract")
    pytesseract.image_to_string = lambda _: " Direct image OCR text \n"
    monkeypatch.setitem(sys.modules, "PIL", pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", pil_image)
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract)

    assert extract_text_from_image_bytes(b"image bytes") == "Direct image OCR text"

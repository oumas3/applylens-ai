import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import main as main_module
from app.config import Settings, get_settings
from app.routers import documents as documents_router
from app.routers import opportunities as opportunities_router
from app.routers import reviews as reviews_router
from app.routers import tasks as tasks_router
from app.routers import profiles as profiles_router
from app.routers.auth import get_current_user

from io import BytesIO
from uuid import UUID

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_persistent_state(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Keep each test independent from local runtime JSON storage."""
    monkeypatch.setenv("RETRIEVAL_PROVIDER", "lexical")
    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: {"id": "test-user", "email": "test@example.com", "is_active": True},
    )
    get_settings.cache_clear()
    monkeypatch.setattr(
        documents_router,
        "DOCUMENTS_FILE",
        tmp_path / "documents.json",
    )
    monkeypatch.setattr(reviews_router, "REVIEWS_FILE", tmp_path / "reviews.json")
    monkeypatch.setattr(tasks_router, "TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(
        opportunities_router,
        "OPPORTUNITIES_FILE",
        tmp_path / "opportunities.json",
    )
    monkeypatch.setattr(profiles_router, "PROFILES_FILE", tmp_path / "profiles.json")

    reviews_router.reviews[:] = []
    tasks_router.tasks[:] = [
        task.model_copy(update={"user_id": "test-user"})
        for task in tasks_router.DEFAULT_TASKS
    ]
    documents_router.documents.clear()
    opportunities_router.ingested_opportunities.clear()
    opportunities_router._retrieval_cache.clear()
    profiles_router.profiles.clear()

def test_upload_document_rejects_corrupted_pdf() -> None:
    response = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "broken.pdf",
                b"%PDF-1.4\nbroken\n%%EOF",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "The PDF could not be read."

    
def make_test_pdf(text: str = "Hello from PDF") -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)

    content = DecodedStreamObject()
    content.set_data(
        f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    )
    content_reference = writer._add_object(content)

    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_reference}
            )
        }
    )
    page[NameObject("/Contents")] = content_reference

    writer.write(output)
    return output.getvalue()


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "applylens-api"
    assert isinstance(payload["environment"], str)
    assert payload["environment"]


def test_health_response_includes_generated_request_id() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert str(UUID(response.headers["x-request-id"])) == response.headers["x-request-id"]


def test_health_response_preserves_safe_request_id() -> None:
    response = client.get("/health", headers={"X-Request-ID": "applylens-test-123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "applylens-test-123"


def test_health_response_replaces_unsafe_request_id() -> None:
    response = client.get("/health", headers={"X-Request-ID": "unsafe request id"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "unsafe request id"
    UUID(response.headers["x-request-id"])


def test_cors_preflight_is_traced(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="applylens.request")
    main_module.request_logger.addHandler(caplog.handler)

    try:
        response = client.options(
            "/api/v1/documents",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "X-Request-ID": "applylens-preflight-123",
            },
        )
    finally:
        main_module.request_logger.removeHandler(caplog.handler)

    record = next(item for item in caplog.records if item.name == "applylens.request")
    payload = json.loads(record.message)
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "applylens-preflight-123"
    assert payload["method"] == "OPTIONS"
    assert payload["request_id"] == "applylens-preflight-123"


def test_access_log_is_structured_and_omits_query_string(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="applylens.request")
    main_module.request_logger.addHandler(caplog.handler)

    try:
        response = client.get("/health?private=value")
    finally:
        main_module.request_logger.removeHandler(caplog.handler)

    record = next(item for item in caplog.records if item.name == "applylens.request")
    payload = json.loads(record.message)
    assert response.status_code == 200
    assert payload["event"] == "http_request"
    assert payload["path"] == "/health"
    assert payload["status_code"] == 200
    assert payload["request_id"] == response.headers["x-request-id"]
    assert "private" not in record.message


def test_request_logger_has_a_dedicated_output_handler() -> None:
    assert main_module.request_logger.handlers
    assert main_module.request_logger.propagate is False


def test_unhandled_error_response_keeps_request_id_and_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_current_user() -> None:
        raise RuntimeError("test failure")

    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        fail_current_user,
    )
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/documents",
        headers={
            "Origin": "http://localhost:5173",
            "X-Request-ID": "applylens-error-123",
        },
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert response.headers["x-request-id"] == "applylens-error-123"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]


def test_readiness_reports_local_retrieval_ready() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "applylens-api",
        "checks": {"api": "ok", "database": "fallback", "retrieval": "ok"},
    }


def test_readiness_reports_database_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        Settings(
            _env_file=None,
            retrieval_storage="memory",
            database_url="postgresql://127.0.0.1:1/applylens",
        ),
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "applylens-api",
        "checks": {"api": "ok", "database": "error"},
    }


def test_readiness_reports_pgvector_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        Settings(
            _env_file=None,
            retrieval_provider="openai",
            openai_api_key="test-key",
            retrieval_storage="pgvector",
            database_url="postgresql://127.0.0.1:1/applylens",
        ),
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"] == "error"


def test_product_scope() -> None:
    response = client.get("/api/v1/product")
    assert response.status_code == 200
    payload = response.json()
    assert payload["supported_opportunities"] == ["Master's", "PhD"]
    assert payload["phase"] == "Sprint 15 — Launch onboarding and accessible workspace"


def test_upload_document_accepts_valid_pdf() -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("resume.pdf", make_test_pdf(), "application/pdf")},
    )

    assert response.status_code == 201

    payload = response.json()
    assert payload["original_filename"] == "resume.pdf"
    assert payload["stored_filename"].endswith(".pdf")
    assert payload["category"] == "OTHER"
    assert payload["content_type"] == "application/pdf"
    assert payload["status"] == "uploaded"
    assert payload["size_bytes"] == len(make_test_pdf())


def test_upload_document_rejects_non_pdf_files() -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("resume.docx", b"not-a-pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Only PDF and TXT documents are accepted."


def test_upload_document_accepts_valid_category() -> None:
    response = client.post(
        "/api/v1/documents?category=CV",
        files={"file": ("cv.pdf", make_test_pdf(), "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json()["category"] == "CV"


def test_upload_document_rejects_invalid_category() -> None:
    response = client.post(
        "/api/v1/documents?category=INVALID",
        files={"file": ("cv.pdf", make_test_pdf(), "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid document category."


def test_upload_document_rejects_empty_files() -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded file is empty."


def test_upload_document_rejects_files_over_10_mb() -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("large.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "The file must not exceed 10 MB."


def test_upload_document_rejects_path_traversal_filenames() -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("../evil.pdf", make_test_pdf(), "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid filename."


def test_list_documents_returns_uploaded_metadata() -> None:
    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_document_metadata_can_be_reloaded_from_persistent_storage() -> None:
    upload_response = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"persistent notes", "text/plain")},
    )
    document_id = upload_response.json()["id"]

    documents_router.documents.clear()
    documents_router.documents.update(documents_router._load_documents())

    response = client.get(f"/api/v1/documents/{document_id}")

    assert response.status_code == 200
    assert response.json()["id"] == document_id


def test_upload_document_extracts_text_from_txt_files() -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"hello world\n", "text/plain")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["content_type"] == "text/plain"
    assert payload["extracted_text_length"] == len("hello world\n")


def test_upload_document_accepts_txt_content_types_with_charset() -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"hello from charset", "text/plain; charset=utf-8")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["content_type"] == "text/plain"
    assert payload["extracted_text_length"] == len("hello from charset")

def test_upload_document_extracts_text_from_simple_pdf_payloads() -> None:
    pdf_bytes = make_test_pdf("Hello from PDF")
    response = client.post(
        "/api/v1/documents",
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["content_type"] == "application/pdf"
    assert payload["extracted_text_length"] == len("Hello from PDF")


def test_get_document_text_returns_extracted_content() -> None:
    upload_response = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"hello from text endpoint", "text/plain")},
    )

    document_id = upload_response.json()["id"]
    response = client.get(f"/api/v1/documents/{document_id}/text")

    assert response.status_code == 200
    assert response.text == "hello from text endpoint"


def test_delete_document_removes_metadata_and_file() -> None:
    upload_response = client.post(
        "/api/v1/documents",
        files={"file": ("delete-me.pdf", make_test_pdf(), "application/pdf")},
    )

    document_id = upload_response.json()["id"]
    delete_response = client.delete(f"/api/v1/documents/{document_id}")
    get_response = client.get(f"/api/v1/documents/{document_id}")

    assert upload_response.status_code == 201
    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_analyse_opportunity_returns_structured_review() -> None:
    response = client.post(
        "/api/v1/opportunities/analyse",
        json={
            "title": "PhD in AI",
            "requirements": [
                "Bachelor's degree",
                "Research experience",
                "English proficiency",
            ],
            "evidence": [
                "Bachelor's degree completed",
                "Published two papers",
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "PhD in AI"
    assert payload["eligibility"] == "Action required"
    assert payload["matched_requirements"] == ["Bachelor's degree", "Research experience"]
    assert payload["missing_requirements"] == ["English proficiency"]
    assert payload["evidence_summary"] == [
        "Bachelor's degree completed",
        "Published two papers",
    ]
    assert payload["requirement_results"] == [
        {
            "requirement": "Bachelor's degree",
            "status": "Eligible",
            "evidence": ["Bachelor's degree completed"],
            "explanation": "Supporting evidence was found in the provided profile.",
            "action": None,
        },
        {
            "requirement": "Research experience",
            "status": "Eligible",
            "evidence": ["Published two papers"],
            "explanation": "Supporting evidence was found in the provided profile.",
            "action": None,
        },
        {
            "requirement": "English proficiency",
            "status": "Action required",
            "evidence": [],
            "explanation": "No supporting evidence was found in the provided profile.",
            "action": "Provide evidence for: English proficiency",
        },
    ]


def test_ingest_opportunity_stores_source_text_and_metadata() -> None:
    response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "PhD in AI",
            "source_text": "Applicants must hold a bachelor's degree.",
            "institution": "Example University",
            "degree_type": "PhD",
            "source_name": "2026 doctoral call",
            "source_url": "https://example.edu/call",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"]
    assert payload["title"] == "PhD in AI"
    assert payload["source_text"] == "Applicants must hold a bachelor's degree."
    assert payload["institution"] == "Example University"
    assert payload["source_url"] == "https://example.edu/call"
    assert payload["requirements"] == [
        "Applicants must hold a bachelor's degree."
    ]
    assert payload["requirement_citations"] == [
        {
            "requirement": "Applicants must hold a bachelor's degree.",
            "source_name": "2026 doctoral call",
            "page": None,
        }
    ]

    list_response = client.get("/api/v1/opportunities/ingested")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == payload["id"]
    assert opportunities_router.OPPORTUNITIES_FILE.exists()


def test_ingested_opportunity_persistence_file_is_isolated_per_test() -> None:
    assert not opportunities_router.OPPORTUNITIES_FILE.exists()


def test_ingest_opportunity_rejects_empty_source_text() -> None:
    response = client.post(
        "/api/v1/opportunities/ingest",
        json={"title": "PhD in AI", "source_text": ""},
    )

    assert response.status_code == 422


def test_ingest_opportunity_file_extracts_txt_and_parses_requirements() -> None:
    response = client.post(
        "/api/v1/opportunities/ingest-file",
        data={"title": "MSc Data Science", "degree_type": "MSc"},
        files={
            "file": (
                "call.txt",
                b"Applicants must hold a bachelor's degree.",
                "text/plain",
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_name"] == "call.txt"
    assert payload["source_text"] == "Applicants must hold a bachelor's degree."
    assert payload["requirements"] == [
        "Applicants must hold a bachelor's degree."
    ]
    assert payload["requirement_citations"] == [
        {
            "requirement": "Applicants must hold a bachelor's degree.",
            "source_name": "call.txt",
            "page": None,
        }
    ]


def test_ingest_opportunity_file_extracts_pdf_text() -> None:
    response = client.post(
        "/api/v1/opportunities/ingest-file",
        data={"title": "PhD in AI"},
        files={"file": ("call.pdf", make_test_pdf("Research experience required"), "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json()["source_text"] == "Research experience required"
    assert response.json()["requirement_citations"] == [
        {
            "requirement": "Research experience required",
            "source_name": "call.pdf",
            "page": 1,
        }
    ]


def test_ingest_opportunity_file_rejects_unsupported_type() -> None:
    response = client.post(
        "/api/v1/opportunities/ingest-file",
        data={"title": "PhD in AI"},
        files={"file": ("call.docx", b"not supported", "application/octet-stream")},
    )

    assert response.status_code == 415


def test_ingest_opportunity_file_rejects_files_over_10_mb() -> None:
    response = client.post(
        "/api/v1/opportunities/ingest-file",
        data={"title": "PhD in AI"},
        files={"file": ("large.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "The file must not exceed 10 MB."


def test_ingest_opportunity_extracts_requirement_lines() -> None:
    response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "MSc Data Science",
            "source_text": (
                "Requirements:\n"
                "- Applicants must hold a bachelor's degree.\n"
                "- English proficiency required.\n"
                "Campus housing available."
            ),
        },
    )

    assert response.status_code == 201
    assert response.json()["requirements"] == [
        "Applicants must hold a bachelor's degree.",
        "English proficiency required.",
    ]


def test_ingest_opportunity_extracts_deadline_and_funding() -> None:
    response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "MSc Data Science",
            "source_text": (
                "Application deadline: 15 September 2026\n"
                "Funding: Full scholarship and stipend available."
            ),
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["deadline"] == "15 September 2026"
    assert payload["deadline_date"] == "2026-09-15"
    assert payload["funding"] == "Funding: Full scholarship and stipend available."


def test_analyse_ingested_opportunity_reuses_deadline_and_funding() -> None:
    ingest_response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "PhD in AI",
            "source_text": (
                "Applicants must hold a master's degree.\n"
                "Deadline: 2026-10-01\n"
                "No funding available."
            ),
        },
    )
    opportunity_id = ingest_response.json()["id"]

    response = client.post(
        f"/api/v1/opportunities/ingested/{opportunity_id}/analyse",
        json={"evidence": ["Master's degree completed"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deadline"] == "2026-10-01"
    assert payload["deadline_date"] == "2026-10-01"
    assert payload["funding"] == "No funding available."
    assert payload["funding_status"] == "unavailable"


def test_end_to_end_application_review_workflow() -> None:
    document_response = client.post(
        "/api/v1/documents",
        files={"file": ("profile.txt", b"Bachelor's degree completed", "text/plain")},
    )
    document_id = document_response.json()["id"]

    opportunity_response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "MSc Data Science",
            "source_text": (
                "Applicants must hold a bachelor's degree.\n"
                "English proficiency required.\n"
                "Application deadline: 15 September 2026.\n"
                "Funding: Scholarship available."
            ),
        },
    )
    opportunity_id = opportunity_response.json()["id"]

    evidence_response = client.post(
        f"/api/v1/opportunities/ingested/{opportunity_id}/evidence-search",
        json={"query": "English proficiency"},
    )
    assert evidence_response.status_code == 200
    assert evidence_response.json()

    analysis_response = client.post(
        f"/api/v1/opportunities/ingested/{opportunity_id}/analyse",
        json={"document_ids": [document_id]},
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()
    assert analysis["eligibility"] == "Action required"
    assert analysis["deadline_date"] == "2026-09-15"
    assert analysis["funding_status"] == "available"

    task_response = client.post(
        "/api/v1/tasks/generate",
        json={
            "opportunity_id": opportunity_id,
            "missing_requirements": analysis["missing_requirements"],
        },
    )
    assert task_response.status_code == 200
    assert task_response.json()[0]["opportunity_id"] == opportunity_id

    first_review = {
        "id": 201,
        "title": analysis["title"],
        "eligibility": analysis["eligibility"],
        "matched_requirements": analysis["matched_requirements"],
        "missing_requirements": analysis["missing_requirements"],
    }
    second_review = {**first_review, "id": 202, "eligibility": "Eligible"}
    assert client.post("/api/v1/reviews", json=first_review).status_code == 201
    assert client.post("/api/v1/reviews", json=second_review).status_code == 201

    comparison_response = client.post(
        "/api/v1/reviews/compare",
        json={"review_ids": [201, 202]},
    )
    assert comparison_response.status_code == 200
    assert comparison_response.json()["recommended_review_id"] == 202


def test_analyse_ingested_opportunity_reuses_parsed_requirements() -> None:
    ingest_response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "MSc Data Science",
            "source_text": (
                "Applicants must hold a bachelor's degree.\n"
                "English proficiency required."
            ),
        },
    )
    opportunity_id = ingest_response.json()["id"]

    response = client.post(
        f"/api/v1/opportunities/ingested/{opportunity_id}/analyse",
        json={
            "evidence": [
                "Bachelor's degree completed",
                "IELTS proficiency confirmed",
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "MSc Data Science"
    assert payload["eligibility"] == "Eligible"
    assert payload["matched_requirements"] == [
        "Applicants must hold a bachelor's degree.",
        "English proficiency required.",
    ]
    assert payload["source_citations"] == [
        {
            "requirement": "Applicants must hold a bachelor's degree.",
            "source_name": None,
            "page": None,
        },
        {
            "requirement": "English proficiency required.",
            "source_name": None,
            "page": None,
        },
    ]


def test_analyse_ingested_opportunity_rejects_unknown_id() -> None:
    response = client.post(
        "/api/v1/opportunities/ingested/missing/analyse",
        json={"evidence": []},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingested opportunity not found."


def test_delete_ingested_opportunity_removes_saved_record() -> None:
    ingest_response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "MSc Data Science",
            "source_text": "Applicants must hold a bachelor's degree.",
        },
    )
    opportunity_id = ingest_response.json()["id"]

    delete_response = client.delete(
        f"/api/v1/opportunities/ingested/{opportunity_id}"
    )
    list_response = client.get("/api/v1/opportunities/ingested")

    assert delete_response.status_code == 204
    assert list_response.json() == []


def test_delete_ingested_opportunity_rejects_unknown_id() -> None:
    response = client.delete("/api/v1/opportunities/ingested/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingested opportunity not found."


def test_search_ingested_opportunity_returns_traceable_evidence_chunks() -> None:
    ingest_response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "PhD in AI",
            "source_text": (
                "English proficiency required.\n\n"
                "Funding information is available."
            ),
            "source_name": "call.txt",
        },
    )
    opportunity_id = ingest_response.json()["id"]

    response = client.post(
        f"/api/v1/opportunities/ingested/{opportunity_id}/evidence-search",
        json={
            "query": "English proficiency required.\n\nFunding information is available.",
            "top_k": 1,
        },
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["chunk"]["source_name"] == "call.txt"
    assert results[0]["score"] > 0


def test_search_ingested_opportunity_rejects_unknown_id() -> None:
    response = client.post(
        "/api/v1/opportunities/ingested/missing/evidence-search",
        json={"query": "degree"},
    )

    assert response.status_code == 404


def test_search_ingested_opportunity_ranks_matching_evidence_first() -> None:
    ingest_response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "MSc Data Science",
            "source_text": (
                "English proficiency is required for admission.\n\n"
                "A scholarship may be available."
            ),
            "source_name": "call.txt",
        },
    )
    opportunity_id = ingest_response.json()["id"]

    response = client.post(
        f"/api/v1/opportunities/ingested/{opportunity_id}/evidence-search",
        json={"query": "English proficiency", "top_k": 1},
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert "English proficiency" in results[0]["chunk"]["text"]


def test_search_ingested_opportunity_reuses_cached_index() -> None:
    ingest_response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "MSc Data Science",
            "source_text": "English proficiency is required.",
        },
    )
    opportunity_id = ingest_response.json()["id"]
    search_url = (
        f"/api/v1/opportunities/ingested/{opportunity_id}/evidence-search"
    )

    first_response = client.post(
        search_url,
        json={"query": "English proficiency", "top_k": 1},
    )
    second_response = client.post(
        search_url,
        json={"query": "required", "top_k": 1},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert list(opportunities_router._retrieval_cache) == [opportunity_id]


def test_search_ingested_opportunity_returns_empty_for_unrelated_query() -> None:
    ingest_response = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "MSc Data Science",
            "source_text": "English proficiency is required.",
        },
    )
    opportunity_id = ingest_response.json()["id"]

    response = client.post(
        f"/api/v1/opportunities/ingested/{opportunity_id}/evidence-search",
        json={"query": "housing requirement", "top_k": 5},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_search_ingested_opportunity_rejects_invalid_top_k() -> None:
    ingest_response = client.post(
        "/api/v1/opportunities/ingest",
        json={"title": "MSc Data Science", "source_text": "Requirements."},
    )
    opportunity_id = ingest_response.json()["id"]

    response = client.post(
        f"/api/v1/opportunities/ingested/{opportunity_id}/evidence-search",
        json={"query": "requirements", "top_k": 21},
    )

    assert response.status_code == 422


def test_analyse_opportunity_uses_uploaded_document_evidence() -> None:
    upload_response = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "profile.txt",
                b"Bachelor's degree completed\nIELTS proficiency confirmed",
                "text/plain",
            )
        },
    )

    document_id = upload_response.json()["id"]
    response = client.post(
        "/api/v1/opportunities/analyse",
        json={
            "title": "PhD in AI",
            "requirements": ["Bachelor's degree", "English proficiency"],
            "document_ids": [document_id],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["eligibility"] == "Eligible"
    assert payload["matched_requirements"] == [
        "Bachelor's degree",
        "English proficiency",
    ]
    assert len(payload["evidence_summary"]) == 1


def test_analyse_opportunity_marks_explicitly_failed_requirement_not_eligible() -> None:
    response = client.post(
        "/api/v1/opportunities/analyse",
        json={
            "title": "PhD in AI",
            "requirements": ["Bachelor's degree", "English proficiency"],
            "evidence": [
                "No bachelor's degree has been completed",
                "IELTS proficiency confirmed",
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["eligibility"] == "Not eligible"
    assert payload["requirement_results"][0]["status"] == "Not eligible"
    assert payload["requirement_results"][0]["evidence"] == [
        "No bachelor's degree has been completed"
    ]


def test_analyse_opportunity_normalizes_deadline_and_funding() -> None:
    response = client.post(
        "/api/v1/opportunities/analyse",
        json={
            "title": "PhD in AI",
            "requirements": [],
            "deadline": "24 July 2026",
            "deadline_date": "2026-07-24",
            "funding": "Scholarship available",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deadline"] == "24 July 2026"
    assert payload["deadline_date"] == "2026-07-24"
    assert payload["funding"] == "Scholarship available"
    assert payload["funding_status"] == "available"


def test_analyse_opportunity_returns_structured_opportunity_metadata() -> None:
    response = client.post(
        "/api/v1/opportunities/analyse",
        json={
            "title": "PhD in AI",
            "institution": "Example University",
            "degree_type": "PhD",
            "application_url": "https://example.edu/apply",
            "required_documents": ["CV", " Transcript "],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["institution"] == "Example University"
    assert payload["degree_type"] == "PhD"
    assert payload["application_url"] == "https://example.edu/apply"
    assert payload["required_documents"] == ["CV", "Transcript"]


def test_analyse_opportunity_rejects_invalid_application_url() -> None:
    response = client.post(
        "/api/v1/opportunities/analyse",
        json={
            "title": "PhD in AI",
            "application_url": "not-a-url",
        },
    )

    assert response.status_code == 422


def test_save_review_rejects_unknown_eligibility_status() -> None:
    response = client.post(
        "/api/v1/reviews",
        json={
            "id": 301,
            "title": "MSc Data Science",
            "eligibility": "Maybe",
        },
    )

    assert response.status_code == 422


def test_compare_reviews_requires_two_review_ids() -> None:
    response = client.post(
        "/api/v1/reviews/compare",
        json={"review_ids": [301]},
    )

    assert response.status_code == 422


def test_analyse_opportunity_rejects_unknown_document() -> None:
    response = client.post(
        "/api/v1/opportunities/analyse",
        json={
            "title": "PhD in AI",
            "requirements": ["Research experience"],
            "document_ids": ["missing-document"],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found: missing-document"


def test_list_tasks_returns_default_tasks() -> None:
    response = client.get("/api/v1/tasks")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload
    assert {item["status"] for item in payload} <= {
        "pending",
        "in_progress",
        "completed",
    }


def test_generate_tasks_from_missing_requirements_and_opportunity_metadata() -> None:
    response = client.post(
        "/api/v1/tasks/generate",
        json={
            "missing_requirements": ["English proficiency", "Research proposal"],
            "deadline": "24 July 2026",
            "funding": "Scholarship available",
        },
    )

    assert response.status_code == 200
    assert response.json() == [
            {
                "id": 1,
                "user_id": "test-user",
                "opportunity_id": None,
            "title": "Provide evidence for: English proficiency",
            "status": "pending",
        },
            {
                "id": 2,
                "user_id": "test-user",
                "opportunity_id": None,
            "title": "Provide evidence for: Research proposal",
            "status": "pending",
        },
            {
                "id": 3,
                "user_id": "test-user",
                "opportunity_id": None,
            "title": "Confirm application deadline: 24 July 2026",
            "status": "pending",
        },
            {
                "id": 4,
                "user_id": "test-user",
                "opportunity_id": None,
            "title": "Review funding requirements and available support",
            "status": "pending",
        },
    ]


def test_generate_tasks_keeps_different_opportunities_separate() -> None:
    first = client.post(
        "/api/v1/tasks/generate",
        json={
            "opportunity_id": "opportunity-a",
            "missing_requirements": ["Research proposal"],
        },
    )
    second = client.post(
        "/api/v1/tasks/generate",
        json={
            "opportunity_id": "opportunity-b",
            "missing_requirements": ["English proficiency"],
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()[0]["opportunity_id"] == "opportunity-a"
    assert second.json()[0]["opportunity_id"] == "opportunity-b"
    assert first.json()[0]["id"] != second.json()[0]["id"]
    assert {
        task["opportunity_id"] for task in client.get("/api/v1/tasks").json()
    } >= {"opportunity-a", "opportunity-b"}


def test_update_task_status_changes_task_state() -> None:
    response = client.patch(
        "/api/v1/tasks/1",
        json={"status": "in_progress"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


def test_update_task_status_rejects_unknown_task() -> None:
    response = client.patch(
        "/api/v1/tasks/9999",
        json={"status": "completed"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found."


def test_saved_reviews_endpoint_returns_recent_reviews() -> None:
    response = client.get("/api/v1/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)


def test_save_review_persists_review_for_future_reads() -> None:
    review = {
        "id": 101,
        "title": "PhD in AI",
        "eligibility": "Eligible",
        "matched_requirements": ["Bachelor's degree"],
        "missing_requirements": [],
        "deadline": "24 July 2026",
        "funding": "Scholarship available",
    }
    review["user_id"] = "test-user"

    save_response = client.post("/api/v1/reviews", json=review)
    list_response = client.get("/api/v1/reviews")

    assert save_response.status_code == 201
    assert save_response.json() == review
    assert list_response.json()[-1] == review


def test_compare_reviews_recommends_eligible_review_with_fewer_gaps() -> None:
    client.post(
        "/api/v1/reviews",
        json={
            "id": 201,
            "title": "MSc Data Science",
            "eligibility": "Action required",
            "matched_requirements": ["Degree"],
            "missing_requirements": ["English proficiency"],
        },
    )
    client.post(
        "/api/v1/reviews",
        json={
            "id": 202,
            "title": "PhD Artificial Intelligence",
            "eligibility": "Eligible",
            "matched_requirements": ["Degree", "English proficiency"],
            "missing_requirements": [],
        },
    )

    response = client.post(
        "/api/v1/reviews/compare",
        json={"review_ids": [201, 202]},
    )

    assert response.status_code == 200
    assert response.json()["recommended_review_id"] == 202

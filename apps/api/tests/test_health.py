from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "applylens-api"
    assert isinstance(payload["environment"], str)
    assert payload["environment"]


def test_product_scope() -> None:
    response = client.get("/api/v1/product")
    assert response.status_code == 200
    assert response.json()["supported_opportunities"] == ["Master's", "PhD"]


def test_upload_document_accepts_valid_pdf() -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("resume.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 201

    payload = response.json()
    assert payload["original_filename"] == "resume.pdf"
    assert payload["stored_filename"].endswith(".pdf")
    assert payload["category"] == "OTHER"
    assert payload["content_type"] == "application/pdf"
    assert payload["status"] == "uploaded"
    assert payload["size_bytes"] == len(b"%PDF-1.4\n")


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
        files={"file": ("cv.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json()["category"] == "CV"


def test_upload_document_rejects_invalid_category() -> None:
    response = client.post(
        "/api/v1/documents?category=INVALID",
        files={"file": ("cv.pdf", b"%PDF-1.4\n", "application/pdf")},
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


def test_upload_document_rejects_path_traversal_filenames() -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("../evil.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid filename."


def test_list_documents_returns_uploaded_metadata() -> None:
    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_upload_document_extracts_text_from_txt_files() -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"hello world\n", "text/plain")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["content_type"] == "text/plain"
    assert payload["extracted_text_length"] == len("hello world\n")


def test_delete_document_removes_metadata_and_file() -> None:
    upload_response = client.post(
        "/api/v1/documents",
        files={"file": ("delete-me.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    document_id = upload_response.json()["id"]
    delete_response = client.delete(f"/api/v1/documents/{document_id}")
    get_response = client.get(f"/api/v1/documents/{document_id}")

    assert upload_response.status_code == 201
    assert delete_response.status_code == 204
    assert get_response.status_code == 404

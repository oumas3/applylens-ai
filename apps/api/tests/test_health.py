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
    assert payload["filename"] == "resume.pdf"
    assert payload["content_type"] == "application/pdf"
    assert payload["status"] == "uploaded"
    assert payload["size_bytes"] == len(b"%PDF-1.4\n")


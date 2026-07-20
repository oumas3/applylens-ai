from fastapi.testclient import TestClient

from app.main import app

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


client = TestClient(app)

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


def test_product_scope() -> None:
    response = client.get("/api/v1/product")
    assert response.status_code == 200
    assert response.json()["supported_opportunities"] == ["Master's", "PhD"]


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
    pdf_bytes = (
        make_test_pdf()
        b"1 0 obj\n"
        b"<< /Type /Catalog /Pages 2 0 R >>\n"
        b"endobj\n"
        b"2 0 obj\n"
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n"
        b"endobj\n"
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
        b"endobj\n"
        b"4 0 obj\n"
        b"<< /Length 44 >>\n"
        b"stream\n"
        b"BT\n/F1 24 Tf\n72 720 Td\n(Hello from PDF) Tj\nET\n"
        b"endstream\n"
        b"endobj\n"
        b"5 0 obj\n"
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        b"endobj\n"
        b"xref\n"
        b"trailer\n"
        b"<< /Root 1 0 R >>\n"
        b"%%EOF"
    )

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

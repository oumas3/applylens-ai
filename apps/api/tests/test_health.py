from fastapi.testclient import TestClient

from app.main import app

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


client = TestClient(app)

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
    assert payload[0]["title"] == "Gather supporting documents"
    assert payload[0]["status"] == "pending"


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
            "title": "Provide evidence for: English proficiency",
            "status": "pending",
        },
        {
            "id": 2,
            "title": "Provide evidence for: Research proposal",
            "status": "pending",
        },
        {
            "id": 3,
            "title": "Confirm application deadline: 24 July 2026",
            "status": "pending",
        },
        {
            "id": 4,
            "title": "Review funding requirements and available support",
            "status": "pending",
        },
    ]


def test_saved_reviews_endpoint_returns_recent_reviews() -> None:
    response = client.get("/api/v1/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload == []

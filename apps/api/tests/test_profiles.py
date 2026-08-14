import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.auth import get_current_user
from app.routers import documents as documents_router
from app.routers import opportunities as opportunities_router
from app.routers import profiles as profiles_router
from app.services.file_storage import LocalFileStorage


@pytest.fixture()
def profile_client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    current = {
        "user": {
            "id": "user-a",
            "email": "a@example.com",
            "is_active": True,
            "external_ai_consent": False,
        }
    }
    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: current["user"],
    )
    monkeypatch.setattr(profiles_router, "PROFILES_FILE", tmp_path / "profiles.json")
    monkeypatch.setattr(profiles_router, "application_store", None)
    monkeypatch.setattr(documents_router, "DOCUMENTS_FILE", tmp_path / "documents.json")
    monkeypatch.setattr(documents_router, "application_store", None)
    storage = LocalFileStorage(tmp_path / "uploads")
    monkeypatch.setattr(documents_router, "file_storage", storage)
    monkeypatch.setattr(opportunities_router, "file_storage", storage)
    profiles_router.profiles.clear()
    documents_router.documents.clear()

    with TestClient(app) as client:
        yield client, current

    app.dependency_overrides.pop(get_current_user, None)
    profiles_router.profiles.clear()
    documents_router.documents.clear()


def _upload(client: TestClient, name: str = "cv.txt") -> str:
    response = client.post(
        "/api/v1/documents?category=CV",
        files={
            "file": (
                name,
                b"Master degree. Research assistant. English fluent. Python.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _profile_payload(document_id: str) -> dict:
    return {
        "full_name": "Candidate Example",
        "headline": "AI research candidate",
        "location": "Casablanca, Morocco",
        "summary": "Interested in evidence-based machine learning.",
        "education": [
            {
                "id": "education-1",
                "institution": "Example University",
                "degree": "Master's degree",
                "field_of_study": "Artificial Intelligence",
                "start_year": 2022,
                "end_year": 2024,
                "grade": "Distinction",
                "document_ids": [document_id],
            }
        ],
        "work_experience": [
            {
                "id": "work-1",
                "organization": "Example Labs",
                "role": "Data Scientist",
                "description": "Built research prototypes.",
                "start_year": 2024,
                "document_ids": [document_id],
            }
        ],
        "research_experience": [
            {
                "id": "research-1",
                "title": "Research assistant",
                "organization": "Example University",
                "description": "Published machine-learning experiments.",
                "start_year": 2023,
                "end_year": 2024,
                "document_ids": [document_id],
            }
        ],
        "languages": [
            {
                "id": "language-1",
                "name": "English",
                "proficiency": "fluent",
                "document_ids": [document_id],
            }
        ],
        "skills": [
            {
                "id": "skill-1",
                "name": "Python",
                "document_ids": [document_id, document_id],
            }
        ],
        "publications": [
            {
                "id": "publication-1",
                "title": "Evidence-aware application systems",
                "venue": "Example Conference",
                "year": 2025,
                "url": "https://example.com/paper",
                "document_ids": [document_id],
            }
        ],
    }


def test_empty_profile_is_tenant_scoped_and_has_all_sections(profile_client) -> None:
    client, _ = profile_client

    response = client.get("/api/v1/profile")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user-a",
        "updated_at": None,
        "full_name": None,
        "headline": None,
        "location": None,
        "summary": None,
        "education": [],
        "work_experience": [],
        "research_experience": [],
        "languages": [],
        "skills": [],
        "publications": [],
    }


def test_profile_saves_structured_evidence_and_reloads(profile_client) -> None:
    client, _ = profile_client
    document_id = _upload(client)

    saved = client.put("/api/v1/profile", json=_profile_payload(document_id))

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["user_id"] == "user-a"
    assert payload["education"][0]["degree"] == "Master's degree"
    assert payload["skills"][0]["document_ids"] == [document_id]
    assert payload["updated_at"] is not None

    profiles_router.profiles.clear()
    profiles_router.profiles.update(profiles_router._load_profiles())
    assert client.get("/api/v1/profile").json() == payload


def test_profile_postgres_payload_is_json_serializable(
    profile_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = profile_client
    document_id = _upload(client)
    assert client.put(
        "/api/v1/profile",
        json=_profile_payload(document_id),
    ).status_code == 200

    class CapturingStore:
        records: list[dict] = []

        def replace_profiles(self, records, *, user_id=None) -> None:
            self.records = list(records)

    store = CapturingStore()
    monkeypatch.setattr(profiles_router, "application_store", store)

    profiles_router._persist_profiles("user-a")

    assert store.records[0]["publications"][0]["url"] == "https://example.com/paper"


def test_profile_rejects_foreign_document_and_invalid_years(profile_client) -> None:
    client, current = profile_client
    current["user"] = {
        "id": "user-b",
        "email": "b@example.com",
        "is_active": True,
        "external_ai_consent": False,
    }
    foreign_document_id = _upload(client, "other.txt")
    current["user"] = {
        "id": "user-a",
        "email": "a@example.com",
        "is_active": True,
        "external_ai_consent": False,
    }

    foreign = client.put(
        "/api/v1/profile",
        json={
            "skills": [
                {"id": "skill-1", "name": "Python", "document_ids": [foreign_document_id]}
            ]
        },
    )
    invalid_years = client.put(
        "/api/v1/profile",
        json={
            "education": [
                {
                    "id": "education-1",
                    "institution": "Example University",
                    "degree": "Master's degree",
                    "start_year": 2025,
                    "end_year": 2024,
                }
            ]
        },
    )

    assert foreign.status_code == 422
    assert foreign.json()["detail"]["document_ids"] == [foreign_document_id]
    assert invalid_years.status_code == 422


def test_profiles_are_isolated_between_users(profile_client) -> None:
    client, current = profile_client
    first_document = _upload(client, "first.txt")
    assert client.put(
        "/api/v1/profile",
        json={
            "skills": [
                {"id": "first-skill", "name": "Python", "document_ids": [first_document]}
            ]
        },
    ).status_code == 200

    current["user"] = {
        "id": "user-b",
        "email": "b@example.com",
        "is_active": True,
        "external_ai_consent": False,
    }
    assert client.get("/api/v1/profile").json()["skills"] == []
    second_document = _upload(client, "second.txt")
    assert client.put(
        "/api/v1/profile",
        json={
            "skills": [
                {"id": "second-skill", "name": "R", "document_ids": [second_document]}
            ]
        },
    ).status_code == 200

    current["user"] = {
        "id": "user-a",
        "email": "a@example.com",
        "is_active": True,
        "external_ai_consent": False,
    }
    assert [item["name"] for item in client.get("/api/v1/profile").json()["skills"]] == [
        "Python"
    ]


def test_analysis_uses_only_profile_items_with_live_document_evidence(profile_client) -> None:
    client, _ = profile_client
    document_id = _upload(client)
    assert client.put(
        "/api/v1/profile",
        json={
            "research_experience": [
                {
                    "id": "research-1",
                    "title": "Research assistant",
                    "description": "Published a paper.",
                    "document_ids": [document_id],
                },
                {
                    "id": "research-2",
                    "title": "Quantum biology",
                    "document_ids": [document_id],
                }
            ],
            "skills": [
                {
                    "id": "skill-1",
                    "name": "Quantum computing",
                    "document_ids": [document_id],
                }
            ],
        },
    ).status_code == 200

    supported = client.post(
        "/api/v1/opportunities/analyse",
        json={"title": "PhD", "requirements": ["Research experience"]},
    )
    assert supported.json()["evidence_summary"] == [
        "Research experience: Research assistant. Published a paper. [source: cv.txt]"
    ]
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204
    assert client.get("/api/v1/profile").json()["research_experience"][0][
        "document_ids"
    ] == []
    unsupported = client.post(
        "/api/v1/opportunities/analyse",
        json={"title": "PhD", "requirements": ["Research experience"]},
    )

    assert supported.status_code == 200
    assert supported.json()["eligibility"] == "Eligible"
    assert unsupported.json()["eligibility"] == "Action required"
    assert unsupported.json()["evidence_summary"] == []


def test_profile_can_be_deleted_without_affecting_documents(profile_client) -> None:
    client, _ = profile_client
    document_id = _upload(client)
    assert client.put(
        "/api/v1/profile",
        json={
            "skills": [
                {"id": "skill-1", "name": "Python", "document_ids": [document_id]}
            ]
        },
    ).status_code == 200

    response = client.delete("/api/v1/profile")

    assert response.status_code == 204
    assert client.get("/api/v1/profile").json()["skills"] == []
    assert document_id in documents_router.documents

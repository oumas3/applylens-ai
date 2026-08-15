import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.routers import documents as documents_router
from app.routers import opportunities as opportunities_router
from app.routers import profiles as profiles_router
from app.routers import reviews as reviews_router
from app.routers import tasks as tasks_router
from app.routers.auth import get_current_user
from app.services.file_storage import LocalFileStorage


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_tenant_state(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AUTH_DATABASE_PATH", str(tmp_path / "auth.db"))
    get_settings.cache_clear()
    monkeypatch.setattr(documents_router, "DOCUMENTS_FILE", tmp_path / "documents.json")
    monkeypatch.setattr(documents_router, "file_storage", LocalFileStorage(tmp_path / "uploads"))
    monkeypatch.setattr(
        opportunities_router,
        "OPPORTUNITIES_FILE",
        tmp_path / "opportunities.json",
    )
    monkeypatch.setattr(reviews_router, "REVIEWS_FILE", tmp_path / "reviews.json")
    monkeypatch.setattr(tasks_router, "TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(profiles_router, "PROFILES_FILE", tmp_path / "profiles.json")
    monkeypatch.setattr(documents_router, "application_store", None)
    monkeypatch.setattr(opportunities_router, "application_store", None)
    monkeypatch.setattr(reviews_router, "application_store", None)
    monkeypatch.setattr(tasks_router, "application_store", None)
    monkeypatch.setattr(profiles_router, "application_store", None)
    documents_router.documents.clear()
    opportunities_router.ingested_opportunities.clear()
    opportunities_router._retrieval_cache.clear()
    reviews_router.reviews.clear()
    tasks_router.tasks.clear()
    profiles_router.profiles.clear()
    yield
    app.dependency_overrides.pop(get_current_user, None)
    get_settings.cache_clear()


def test_resource_routes_require_authentication() -> None:
    for path in (
        "/api/v1/documents",
        "/api/v1/opportunities/ingested",
        "/api/v1/reviews",
        "/api/v1/tasks",
        "/api/v1/profile",
    ):
        response = client.get(path)
        assert response.status_code == 401, path


def test_two_user_resource_crud_isolation_matrix() -> None:
    user_a = {"id": "user-a", "email": "a@example.com", "is_active": True}
    user_b = {"id": "user-b", "email": "b@example.com", "is_active": True}
    app.dependency_overrides[get_current_user] = lambda: user_a

    document = client.post(
        "/api/v1/documents",
        files={"file": ("private.txt", b"Private evidence", "text/plain")},
    )
    assert document.status_code == 201
    document_id = document.json()["id"]
    opportunity = client.post(
        "/api/v1/opportunities/ingest",
        json={"title": "Private call", "source_text": "Applicants must have a degree."},
    )
    assert opportunity.status_code == 201
    opportunity_id = opportunity.json()["id"]
    profile = client.put(
        "/api/v1/profile",
        json={
            "skills": [
                {
                    "id": "private-skill",
                    "name": "Python",
                    "document_ids": [document_id],
                }
            ]
        },
    )
    assert profile.status_code == 200
    for review_id in (101, 102):
        assert client.post(
            "/api/v1/reviews",
            json={
                "id": review_id,
                "title": f"Private review {review_id}",
                "eligibility": "Eligible",
            },
        ).status_code == 201
    generated = client.post(
        "/api/v1/tasks/generate",
        json={
            "opportunity_id": opportunity_id,
            "missing_requirements": ["Transcript"],
        },
    )
    assert generated.status_code == 200
    task_id = generated.json()[0]["id"]

    app.dependency_overrides[get_current_user] = lambda: user_b
    assert client.get("/api/v1/documents").json() == []
    assert client.get("/api/v1/opportunities/ingested").json() == []
    assert client.get("/api/v1/reviews").json() == []
    assert client.get("/api/v1/tasks").json() == []
    assert client.get("/api/v1/profile").json()["user_id"] == "user-b"
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
    assert client.get(f"/api/v1/documents/{document_id}/text").status_code == 404
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 404
    assert client.delete(
        f"/api/v1/opportunities/ingested/{opportunity_id}"
    ).status_code == 404
    assert client.post(
        f"/api/v1/opportunities/ingested/{opportunity_id}/analyse",
        json={},
    ).status_code == 404
    assert client.put(
        "/api/v1/profile",
        json={
            "skills": [
                {
                    "id": "stolen-skill",
                    "name": "Python",
                    "document_ids": [document_id],
                }
            ]
        },
    ).status_code == 422
    assert client.post(
        "/api/v1/reviews/compare",
        json={"review_ids": [101, 102]},
    ).status_code == 404
    assert client.delete("/api/v1/reviews/101").status_code == 404
    assert client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "completed"},
    ).status_code == 404
    assert client.delete(f"/api/v1/tasks/{task_id}").status_code == 404

    app.dependency_overrides[get_current_user] = lambda: user_a
    assert len(client.get("/api/v1/documents").json()) == 1
    assert len(client.get("/api/v1/opportunities/ingested").json()) == 1
    assert len(client.get("/api/v1/reviews").json()) == 2
    assert len(client.get("/api/v1/tasks").json()) == 1
    assert client.post(
        "/api/v1/reviews/compare",
        json={"review_ids": [101, 102]},
    ).status_code == 200
    assert client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "completed"},
    ).json()["status"] == "completed"
    assert client.delete(f"/api/v1/tasks/{task_id}").status_code == 204
    assert client.delete("/api/v1/reviews/101").status_code == 204
    assert client.delete(
        f"/api/v1/opportunities/ingested/{opportunity_id}"
    ).status_code == 204
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204
    assert client.delete("/api/v1/profile").status_code == 204

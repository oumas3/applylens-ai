import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import opportunities as opportunities_router
from app.routers.auth import get_current_user


client = TestClient(app)


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


def test_users_cannot_see_each_others_opportunities(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(opportunities_router, "OPPORTUNITIES_FILE", tmp_path / "opportunities.json")
    opportunities_router.ingested_opportunities.clear()
    user_a = {"id": "user-a", "email": "a@example.com", "is_active": True}
    user_b = {"id": "user-b", "email": "b@example.com", "is_active": True}
    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        created = client.post(
            "/api/v1/opportunities/ingest",
            json={"title": "Private call", "source_text": "Applicants must have a degree."},
        )
        assert created.status_code == 201
        opportunity_id = created.json()["id"]

        app.dependency_overrides[get_current_user] = lambda: user_b
        assert client.get("/api/v1/opportunities/ingested").json() == []
        assert client.delete(f"/api/v1/opportunities/ingested/{opportunity_id}").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        opportunities_router.ingested_opportunities.clear()

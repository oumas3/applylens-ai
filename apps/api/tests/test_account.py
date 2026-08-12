import base64
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.routers import documents as documents_router
from app.routers import opportunities as opportunities_router
from app.routers import reviews as reviews_router
from app.routers import tasks as tasks_router
from app.services.file_storage import LocalFileStorage


@pytest.fixture()
def account_client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_DATABASE_PATH", str(tmp_path / "auth.db"))
    get_settings.cache_clear()
    monkeypatch.setattr(documents_router, "DOCUMENTS_FILE", tmp_path / "documents.json")
    monkeypatch.setattr(documents_router, "file_storage", LocalFileStorage(tmp_path / "uploads"))
    monkeypatch.setattr(opportunities_router, "OPPORTUNITIES_FILE", tmp_path / "opportunities.json")
    monkeypatch.setattr(reviews_router, "REVIEWS_FILE", tmp_path / "reviews.json")
    monkeypatch.setattr(tasks_router, "TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(documents_router, "application_store", None)
    monkeypatch.setattr(opportunities_router, "application_store", None)
    monkeypatch.setattr(reviews_router, "application_store", None)
    monkeypatch.setattr(tasks_router, "application_store", None)

    documents_router.documents.clear()
    opportunities_router.ingested_opportunities.clear()
    opportunities_router._retrieval_cache.clear()
    reviews_router.reviews.clear()
    tasks_router.tasks.clear()

    with TestClient(app) as client:
        yield client, tmp_path
    get_settings.cache_clear()


def _register_and_login(client: TestClient, email: str, password: str) -> str:
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert registered.status_code == 201
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert logged_in.status_code == 200
    return registered.json()["id"]


def _add_workspace_data(client: TestClient, label: str) -> tuple[str, bytes]:
    content = f"{label} private document".encode()
    document = client.post(
        "/api/v1/documents?category=CV",
        files={"file": (f"{label}.txt", content, "text/plain")},
    )
    assert document.status_code == 201

    opportunity = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": f"{label} PhD",
            "source_text": "Applicants must provide a degree transcript.",
            "source_name": f"{label}-call.txt",
        },
    )
    assert opportunity.status_code == 201
    opportunity_id = opportunity.json()["id"]

    review = client.post(
        "/api/v1/reviews",
        json={
            "id": 1,
            "title": f"{label} review",
            "eligibility": "Unclear",
            "matched_requirements": [],
            "missing_requirements": ["Transcript"],
        },
    )
    assert review.status_code == 201
    generated = client.post(
        "/api/v1/tasks/generate",
        json={
            "opportunity_id": opportunity_id,
            "missing_requirements": ["Transcript"],
        },
    )
    assert generated.status_code == 200
    return document.json()["stored_filename"], content


def test_account_export_contains_exact_owned_data_only(account_client) -> None:
    client, _ = account_client
    first_id = _register_and_login(client, "first@example.com", "correct horse battery")
    first_filename, first_content = _add_workspace_data(client, "first")
    client.post("/api/v1/auth/logout")

    _register_and_login(client, "second@example.com", "another correct password")
    _add_workspace_data(client, "second")
    client.post("/api/v1/auth/logout")
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "first@example.com", "password": "correct horse battery"},
    ).status_code == 200

    response = client.get("/api/v1/account/export")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="applylens-account-export.json"'
    )
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["schema_version"] == "1.0"
    assert payload["account"]["id"] == first_id
    assert payload["account"]["email"] == "first@example.com"
    assert "password_hash" not in payload["account"]
    assert [item["stored_filename"] for item in payload["documents"]] == [first_filename]
    assert base64.b64decode(payload["documents"][0]["content_base64"]) == first_content
    assert payload["documents"][0]["sha256"] == hashlib.sha256(first_content).hexdigest()
    assert [item["title"] for item in payload["opportunities"]] == ["first PhD"]
    assert [item["title"] for item in payload["reviews"]] == ["first review"]
    assert payload["tasks"]
    assert all(item["user_id"] == first_id for item in payload["tasks"])


def test_external_ai_consent_defaults_off_and_persists(account_client) -> None:
    client, _ = account_client
    _register_and_login(client, "candidate@example.com", "correct horse battery")

    initial = client.get("/api/v1/account/privacy")
    updated = client.put(
        "/api/v1/account/privacy",
        json={"external_ai_consent": True},
    )
    current_user = client.get("/api/v1/auth/me")

    assert initial.status_code == 200
    assert initial.json()["external_ai_consent"] is False
    assert updated.status_code == 200
    assert updated.json()["external_ai_consent"] is True
    assert current_user.json()["external_ai_consent"] is True


def test_openai_evidence_search_requires_explicit_consent(
    account_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = account_client
    _register_and_login(client, "candidate@example.com", "correct horse battery")
    opportunity = client.post(
        "/api/v1/opportunities/ingest",
        json={
            "title": "AI PhD",
            "source_text": "Applicants must provide a degree transcript.",
        },
    )
    monkeypatch.setattr(
        opportunities_router,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            retrieval_provider="openai",
            openai_api_key="test-key",
        ),
    )

    response = client.post(
        f"/api/v1/opportunities/ingested/{opportunity.json()['id']}/evidence-search",
        json={"query": "degree"},
    )

    assert response.status_code == 403
    assert "External AI processing is disabled" in response.json()["detail"]


def test_account_deletion_requires_password_and_preserves_other_tenant(account_client) -> None:
    client, tmp_path = account_client
    first_id = _register_and_login(client, "first@example.com", "correct horse battery")
    first_filename, _ = _add_workspace_data(client, "first")
    client.post("/api/v1/auth/logout")

    second_id = _register_and_login(client, "second@example.com", "another correct password")
    second_filename, _ = _add_workspace_data(client, "second")
    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "first@example.com", "password": "correct horse battery"},
    )

    rejected = client.request(
        "DELETE",
        "/api/v1/account",
        json={"current_password": "wrong password", "confirmation": "DELETE"},
    )
    assert rejected.status_code == 400
    assert (tmp_path / "uploads" / first_filename).exists()

    deleted = client.request(
        "DELETE",
        "/api/v1/account",
        json={"current_password": "correct horse battery", "confirmation": "DELETE"},
    )

    assert deleted.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "first@example.com", "password": "correct horse battery"},
    ).status_code == 401
    assert not (tmp_path / "uploads" / first_filename).exists()
    assert (tmp_path / "uploads" / second_filename).exists()
    assert all(item.user_id != first_id for item in documents_router.documents.values())
    assert all(item.user_id != first_id for item in opportunities_router.ingested_opportunities)
    assert all(item.user_id != first_id for item in reviews_router.reviews)
    assert all(item.user_id != first_id for item in tasks_router.tasks)
    assert any(item.user_id == second_id for item in documents_router.documents.values())


def test_account_routes_require_authentication(account_client) -> None:
    client, _ = account_client

    assert client.get("/api/v1/account/export").status_code == 401
    assert client.get("/api/v1/account/privacy").status_code == 401
    assert client.put(
        "/api/v1/account/privacy",
        json={"external_ai_consent": True},
    ).status_code == 401
    assert client.request(
        "DELETE",
        "/api/v1/account",
        json={"current_password": "correct horse battery", "confirmation": "DELETE"},
    ).status_code == 401

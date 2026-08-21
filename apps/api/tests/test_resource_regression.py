"""Regression tests for Sprint 1 bugfixes.

Covers three defects found in review:
1. ``POST /api/v1/tasks/generate`` with no ``opportunity_id`` used to wipe a
   user's tasks for *every* opportunity, not just the "no opportunity"
   bucket being regenerated.
2. Quota checks on reviews/tasks/documents raced: two concurrent requests
   could both read a stale count and both pass, exceeding the configured
   limit. ``app.concurrency.guarded`` closes that within a single process.
3. ``OpportunityReview.id`` is client-supplied and wasn't checked for
   uniqueness, so a collision could silently alias two different reviews in
   delete/compare lookups.
"""

from concurrent.futures import ThreadPoolExecutor
import time

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

USER = {"id": "user-regression", "email": "regression@example.com", "is_active": True}


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
    app.dependency_overrides[get_current_user] = lambda: USER
    yield
    app.dependency_overrides.pop(get_current_user, None)
    get_settings.cache_clear()


def test_generating_general_tasks_preserves_other_opportunity_tasks() -> None:
    """Regenerating the "no opportunity" task bucket must not wipe tasks
    that belong to a specific opportunity for the same user."""
    scoped = client.post(
        "/api/v1/tasks/generate",
        json={"opportunity_id": "opp-1", "missing_requirements": ["Transcript"]},
    )
    assert scoped.status_code == 200
    assert len(scoped.json()) == 1

    general = client.post(
        "/api/v1/tasks/generate",
        json={"missing_requirements": ["Cover letter"]},
    )
    assert general.status_code == 200

    remaining = client.get("/api/v1/tasks").json()
    opportunity_ids = {task["opportunity_id"] for task in remaining}
    assert "opp-1" in opportunity_ids, (
        "generating general tasks (opportunity_id=None) must not delete "
        "tasks scoped to a different opportunity"
    )
    assert None in opportunity_ids


def test_regenerating_same_scope_still_replaces_only_that_scope() -> None:
    first = client.post(
        "/api/v1/tasks/generate",
        json={"opportunity_id": "opp-1", "missing_requirements": ["Transcript"]},
    ).json()
    other = client.post(
        "/api/v1/tasks/generate",
        json={"opportunity_id": "opp-2", "missing_requirements": ["Reference letter"]},
    ).json()

    regenerated = client.post(
        "/api/v1/tasks/generate",
        json={"opportunity_id": "opp-1", "missing_requirements": ["Budget plan"]},
    ).json()

    remaining = client.get("/api/v1/tasks").json()
    remaining_titles = {task["title"] for task in remaining}
    assert first[0]["title"] not in remaining_titles
    assert other[0]["title"] in remaining_titles
    assert regenerated[0]["title"] in remaining_titles


def test_duplicate_review_id_for_same_user_is_rejected() -> None:
    first = client.post(
        "/api/v1/reviews",
        json={"id": 555, "title": "Grant A", "eligibility": "Eligible"},
    )
    assert first.status_code == 201

    duplicate = client.post(
        "/api/v1/reviews",
        json={"id": 555, "title": "Grant B (different opportunity)", "eligibility": "Unclear"},
    )
    assert duplicate.status_code == 409
    assert len(client.get("/api/v1/reviews").json()) == 1


def test_concurrent_review_saves_cannot_exceed_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Widen the check-then-write race window with an artificial delay and
    fire concurrent saves; the per-user lock in app.concurrency.guarded must
    still enforce the quota exactly."""
    monkeypatch.setenv("FREE_BETA_REVIEW_LIMIT", "1")
    get_settings.cache_clear()

    original_enforce = reviews_router.enforce_account_quota

    def delayed_enforce(resource: str, resulting_count: int) -> None:
        time.sleep(0.05)
        original_enforce(resource, resulting_count)

    monkeypatch.setattr(reviews_router, "enforce_account_quota", delayed_enforce)

    def save(review_id: int):
        return client.post(
            "/api/v1/reviews",
            json={"id": review_id, "title": f"Grant {review_id}", "eligibility": "Eligible"},
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(save, range(1, 6)))

    status_codes = sorted(response.status_code for response in responses)
    assert status_codes == [201, 409, 409, 409, 409]
    assert len(client.get("/api/v1/reviews").json()) == 1

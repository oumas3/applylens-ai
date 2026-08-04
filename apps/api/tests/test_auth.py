import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture()
def auth_client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_DATABASE_PATH", str(tmp_path / "auth.db"))
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def test_register_login_current_user_and_logout(auth_client: TestClient) -> None:
    registered = auth_client.post(
        "/api/v1/auth/register",
        json={"email": "candidate@example.com", "password": "correct horse battery"},
    )
    assert registered.status_code == 201
    assert registered.json()["email"] == "candidate@example.com"
    assert "password" not in registered.json()

    logged_in = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "candidate@example.com", "password": "correct horse battery"},
    )
    assert logged_in.status_code == 200
    assert "applylens_session" in logged_in.cookies

    current = auth_client.get("/api/v1/auth/me")
    assert current.status_code == 200
    assert current.json()["id"] == registered.json()["id"]

    logged_out = auth_client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 204
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_auth_rejects_duplicate_and_invalid_credentials(auth_client: TestClient) -> None:
    payload = {"email": "candidate@example.com", "password": "correct horse battery"}
    assert auth_client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert auth_client.post("/api/v1/auth/register", json=payload).status_code == 409
    assert auth_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "wrong password"},
    ).status_code == 401


def test_current_user_requires_a_session(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/auth/me")
    assert response.status_code == 401

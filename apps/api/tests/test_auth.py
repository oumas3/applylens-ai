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


def test_login_is_blocked_after_repeated_failures(auth_client: TestClient) -> None:
    payload = {"email": "candidate@example.com", "password": "correct horse battery"}
    assert auth_client.post("/api/v1/auth/register", json=payload).status_code == 201

    for _ in range(4):
        response = auth_client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": "wrong password"},
        )
        assert response.status_code == 401

    blocked = auth_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "wrong password"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert "Retry-After" in blocked.headers["access-control-expose-headers"]

    correct_password_is_still_blocked = auth_client.post(
        "/api/v1/auth/login",
        json=payload,
    )
    assert correct_password_is_still_blocked.status_code == 429


def test_password_change_rotates_session_and_credentials(auth_client: TestClient) -> None:
    original = {"email": "candidate@example.com", "password": "correct horse battery"}
    assert auth_client.post("/api/v1/auth/register", json=original).status_code == 201
    assert auth_client.post("/api/v1/auth/login", json=original).status_code == 200
    original_session = auth_client.cookies["applylens_session"]

    changed = auth_client.post(
        "/api/v1/auth/password",
        json={
            "current_password": original["password"],
            "new_password": "a different secure password",
        },
    )

    assert changed.status_code == 204
    assert auth_client.cookies["applylens_session"] != original_session
    assert auth_client.get("/api/v1/auth/me").status_code == 200
    assert auth_client.post("/api/v1/auth/logout").status_code == 204
    assert auth_client.post("/api/v1/auth/login", json=original).status_code == 401
    assert auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": original["email"],
            "password": "a different secure password",
        },
    ).status_code == 200


def test_password_change_rejects_wrong_current_password(auth_client: TestClient) -> None:
    credentials = {"email": "candidate@example.com", "password": "correct horse battery"}
    assert auth_client.post("/api/v1/auth/register", json=credentials).status_code == 201
    assert auth_client.post("/api/v1/auth/login", json=credentials).status_code == 200

    response = auth_client.post(
        "/api/v1/auth/password",
        json={
            "current_password": "incorrect password",
            "new_password": "a different secure password",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "The current password is incorrect."
    assert auth_client.get("/api/v1/auth/me").status_code == 200


def test_password_change_revokes_other_sessions(auth_client: TestClient) -> None:
    credentials = {"email": "candidate@example.com", "password": "correct horse battery"}
    assert auth_client.post("/api/v1/auth/register", json=credentials).status_code == 201
    assert auth_client.post("/api/v1/auth/login", json=credentials).status_code == 200

    with TestClient(app) as other_client:
        assert other_client.post("/api/v1/auth/login", json=credentials).status_code == 200
        assert other_client.get("/api/v1/auth/me").status_code == 200

        changed = auth_client.post(
            "/api/v1/auth/password",
            json={
                "current_password": credentials["password"],
                "new_password": "a different secure password",
            },
        )

        assert changed.status_code == 204
        assert other_client.get("/api/v1/auth/me").status_code == 401


def test_password_change_requires_authentication_and_strong_new_password(
    auth_client: TestClient,
) -> None:
    unauthenticated = auth_client.post(
        "/api/v1/auth/password",
        json={"current_password": "current password", "new_password": "new secure password"},
    )
    assert unauthenticated.status_code == 401

    credentials = {"email": "candidate@example.com", "password": "correct horse battery"}
    assert auth_client.post("/api/v1/auth/register", json=credentials).status_code == 201
    assert auth_client.post("/api/v1/auth/login", json=credentials).status_code == 200
    weak = auth_client.post(
        "/api/v1/auth/password",
        json={"current_password": credentials["password"], "new_password": "too short"},
    )
    assert weak.status_code == 422


def test_password_change_normalizes_whitespace_like_login(auth_client: TestClient) -> None:
    credentials = {"email": "candidate@example.com", "password": "correct horse battery"}
    assert auth_client.post("/api/v1/auth/register", json=credentials).status_code == 201
    assert auth_client.post("/api/v1/auth/login", json=credentials).status_code == 200

    changed = auth_client.post(
        "/api/v1/auth/password",
        json={
            "current_password": f"  {credentials['password']}  ",
            "new_password": "  a different secure password  ",
        },
    )

    assert changed.status_code == 204
    assert auth_client.post("/api/v1/auth/logout").status_code == 204
    assert auth_client.post(
        "/api/v1/auth/login",
        json={
            "email": credentials["email"],
            "password": "a different secure password",
        },
    ).status_code == 200

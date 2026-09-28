from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_static_frontend


def test_static_frontend_mount_is_skipped_without_built_index(tmp_path) -> None:
    application = FastAPI()

    assert mount_static_frontend(application, None) is False
    assert mount_static_frontend(application, tmp_path) is False


def test_static_frontend_serves_built_application(tmp_path) -> None:
    (tmp_path / "index.html").write_text(
        "<h1>ApplyLens demo</h1>",
        encoding="utf-8",
    )
    application = FastAPI()

    assert mount_static_frontend(application, tmp_path) is True

    response = TestClient(application).get("/")

    assert response.status_code == 200
    assert "ApplyLens demo" in response.text

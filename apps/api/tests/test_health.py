from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "applylens-api"}


def test_product_scope() -> None:
    response = client.get("/api/v1/product")
    assert response.status_code == 200
    assert response.json()["supported_opportunities"] == ["Master's", "PhD"]


"""Tests for the foundation endpoints (``GET /`` and ``GET /health``)."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_root_returns_service_info() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["service"]
    assert body["version"]
    assert body["environment"]
    assert body["docs"] == "/docs"


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["environment"]

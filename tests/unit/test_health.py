"""Test health endpoints."""
import pytest


@pytest.mark.api
def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.api
def test_readiness_check(client):
    """Test readiness check endpoint."""
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")

    assert response.status_code == 200
    assert "message" in response.json()
    assert "version" in response.json()

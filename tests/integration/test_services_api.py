"""Integration tests for services API."""
import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.models.base import Base, engine
from src.models.service import Service, ServiceStatus


@pytest.fixture(autouse=True)
def setup_database():
    """Create and drop database for each test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_list_services_empty(client):
    """Test listing services when none exist."""
    response = client.get("/api/services")

    assert response.status_code == 200
    assert response.json() == []


def test_create_service(client):
    """Test creating a new service."""
    data = {
        "name": "myapp.service",
        "description": "My Application",
        "base_url": "http://localhost:8080",
        "port": 8080,
        "health_endpoint": "/health"
    }

    response = client.post("/api/services", json=data)

    assert response.status_code == 201
    json_data = response.json()
    assert json_data["name"] == "myapp.service"
    assert json_data["status"] == "configured"
    assert json_data["id"] is not None


def test_get_service_by_id(client):
    """Test getting a service by ID."""
    # Create service
    create_data = {
        "name": "test.service",
        "description": "Test",
        "base_url": "http://localhost:8080",
        "port": 8080
    }
    create_response = client.post("/api/services", json=create_data)
    service_id = create_response.json()["id"]

    # Get service
    response = client.get(f"/api/services/{service_id}")

    assert response.status_code == 200
    assert response.json()["name"] == "test.service"


def test_update_service(client):
    """Test updating a service."""
    # Create service
    create_data = {
        "name": "test.service",
        "description": "Original",
        "base_url": "http://localhost:8080",
        "port": 8080
    }
    create_response = client.post("/api/services", json=create_data)
    service_id = create_response.json()["id"]

    # Update service
    update_data = {"description": "Updated"}
    response = client.put(f"/api/services/{service_id}", json=update_data)

    assert response.status_code == 200
    assert response.json()["description"] == "Updated"


def test_delete_service(client):
    """Test deleting a service."""
    # Create service
    create_data = {
        "name": "test.service",
        "description": "Test",
        "base_url": "http://localhost:8080",
        "port": 8080
    }
    create_response = client.post("/api/services", json=create_data)
    service_id = create_response.json()["id"]

    # Delete service
    response = client.delete(f"/api/services/{service_id}")

    assert response.status_code == 204

    # Verify deleted
    get_response = client.get(f"/api/services/{service_id}")
    assert get_response.status_code == 404

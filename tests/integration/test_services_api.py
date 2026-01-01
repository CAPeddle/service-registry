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


def test_configure_discovered_service(client):
    """Test configuring a discovered service should update it, not reject it."""
    from sqlalchemy.orm import Session
    from src.models.base import get_db

    # Simulate a discovered service (like from a scan) by directly inserting into DB
    # We need to use the same database session that the API uses
    def override_get_db():
        try:
            db = next(get_db())
            # Create the discovered service
            discovered_service = Service(
                name="finance-tracker.service",
                description=None,
                port=8001,
                base_url=None,
                health_endpoint=None,
                status=ServiceStatus.DISCOVERED,
                systemd_state="active"
            )
            db.add(discovered_service)
            db.commit()
            db.refresh(discovered_service)
            service_id = discovered_service.id
            yield db, service_id
        finally:
            db.close()

    db, service_id = next(override_get_db())

    # User tries to configure it via the UI (POST to /api/services)
    configure_data = {
        "name": "finance-tracker.service",
        "description": "Finance Tracker Application",
        "base_url": "http://192.168.2.48:8001",
        "port": 8001,
        "health_endpoint": "/health"
    }

    response = client.post("/api/services", json=configure_data)

    # Should succeed and update the existing service
    assert response.status_code == 201
    json_data = response.json()
    assert json_data["name"] == "finance-tracker.service"
    assert json_data["description"] == "Finance Tracker Application"
    assert json_data["base_url"] == "http://192.168.2.48:8001"
    assert json_data["status"] == "configured"
    assert json_data["id"] == service_id  # Same ID, updated not created

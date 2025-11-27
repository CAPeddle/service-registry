"""Tests for service schemas."""
import pytest
from pydantic import ValidationError
from src.api.schemas.service_schema import ServiceCreate, ServiceUpdate, ServiceResponse
from src.models.service import ServiceStatus


def test_service_create_valid():
    """Test creating valid service schema."""
    data = {
        "name": "myapp.service",
        "description": "My Application",
        "base_url": "http://localhost:8080",
        "port": 8080,
        "health_endpoint": "/health"
    }
    schema = ServiceCreate(**data)

    assert schema.name == "myapp.service"
    assert schema.description == "My Application"
    assert schema.port == 8080


def test_service_create_validates_port_range():
    """Test that port validation works."""
    with pytest.raises(ValidationError):
        ServiceCreate(
            name="test.service",
            description="Test",
            base_url="http://localhost",
            port=70000  # Invalid port
        )


def test_service_create_validates_url():
    """Test that URL validation works."""
    with pytest.raises(ValidationError):
        ServiceCreate(
            name="test.service",
            description="Test",
            base_url="not-a-url",
            port=8080
        )


def test_service_update_partial():
    """Test partial updates."""
    schema = ServiceUpdate(description="Updated description")

    assert schema.description == "Updated description"
    assert schema.port is None
    assert schema.base_url is None


def test_service_response_from_orm():
    """Test creating response from ORM model."""
    from src.models.service import Service
    from datetime import datetime, UTC

    service = Service(
        id=1,
        name="test.service",
        description="Test Service",
        port=8080,
        base_url="http://localhost:8080",
        health_endpoint="/health",
        status=ServiceStatus.CONFIGURED,
        systemd_state="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    )

    schema = ServiceResponse.model_validate(service)

    assert schema.id == 1
    assert schema.name == "test.service"
    assert schema.status == ServiceStatus.CONFIGURED

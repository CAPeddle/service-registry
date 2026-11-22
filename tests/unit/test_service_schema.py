"""Tests for service schemas."""
import pytest
from pydantic import ValidationError
from src.api.schemas.service_schema import ServiceCreate


def test_service_create_valid():
    """Test creating valid service schema."""
    data = {
        "name": "myapp.service",
        "description": "My Application",
        "base_url": "http://localhost:8080",
        "port": 8080,
        "health_endpoint": "/health",
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
            port=70000,  # Invalid port
        )


def test_service_create_validates_url():
    """Test that URL validation works."""
    with pytest.raises(ValidationError):
        ServiceCreate(name="test.service", description="Test", base_url="not-a-url", port=8080)

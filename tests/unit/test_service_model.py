"""Tests for Service model."""
import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from src.models.service import Service, ServiceStatus
from src.models.base import Base, engine, SessionLocal


@pytest.fixture
def db_session():
    """Create test database session."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_create_service_with_required_fields(db_session):
    """Test creating a service with only required fields."""
    service = Service(
        name="nginx.service",
        status=ServiceStatus.RAW,
        systemd_state="active"
    )
    db_session.add(service)
    db_session.commit()

    assert service.id is not None
    assert service.name == "nginx.service"
    assert service.status == ServiceStatus.RAW
    assert service.systemd_state == "active"
    assert service.created_at is not None
    assert service.updated_at is not None


def test_create_service_with_all_fields(db_session):
    """Test creating a service with all fields."""
    service = Service(
        name="myapp.service",
        description="My web application",
        port=8080,
        health_endpoint="/health",
        base_url="http://192.168.2.24:8080",
        status=ServiceStatus.CONFIGURED,
        systemd_state="active"
    )
    db_session.add(service)
    db_session.commit()

    assert service.description == "My web application"
    assert service.port == 8080
    assert service.health_endpoint == "/health"
    assert service.base_url == "http://192.168.2.24:8080"


def test_service_name_unique_constraint(db_session):
    """Test that service names must be unique."""
    service1 = Service(name="test.service", status=ServiceStatus.RAW, systemd_state="active")
    db_session.add(service1)
    db_session.commit()

    service2 = Service(name="test.service", status=ServiceStatus.RAW, systemd_state="active")
    db_session.add(service2)

    with pytest.raises(IntegrityError):
        db_session.commit()

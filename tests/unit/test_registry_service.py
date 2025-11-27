"""Tests for registry service."""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from src.services.registry_service import RegistryService
from src.services.systemd_discovery import SystemdService
from src.services.port_detection import PortInfo
from src.models.service import Service, ServiceStatus


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return Mock()


@pytest.fixture
def mock_systemd():
    """Create mock systemd discovery."""
    return Mock()


@pytest.fixture
def mock_port_detector():
    """Create mock port detector."""
    return Mock()


@pytest.fixture
def registry(mock_db, mock_systemd, mock_port_detector):
    """Create registry service with mocks."""
    return RegistryService(mock_db, mock_systemd, mock_port_detector)


def test_scan_services_creates_new_discovered_service(registry, mock_systemd, mock_port_detector, mock_db):
    """Test that scan creates new discovered service for web service."""
    # Setup mocks
    mock_systemd.list_services.return_value = [
        SystemdService(name="nginx.service", state="active", description="Web Server")
    ]
    mock_systemd.get_service_pid.return_value = 1234
    mock_port_detector.get_listening_ports.return_value = [
        PortInfo(port=80, pid=1234)
    ]
    mock_port_detector.get_ports_for_pid.return_value = [
        PortInfo(port=80, pid=1234)
    ]
    mock_port_detector.is_web_port.return_value = True
    mock_db.query.return_value.filter.return_value.first.return_value = None

    # Execute
    result = registry.scan_services()

    # Assert
    assert result["total_scanned"] == 1
    assert result["new_discovered"] == 1
    mock_db.add.assert_called_once()
    added_service = mock_db.add.call_args[0][0]
    assert added_service.name == "nginx.service"
    assert added_service.status == ServiceStatus.DISCOVERED
    assert added_service.port == 80


def test_scan_services_updates_existing_service(registry, mock_systemd, mock_port_detector, mock_db):
    """Test that scan updates existing service."""
    existing_service = Service(
        name="nginx.service",
        status=ServiceStatus.CONFIGURED,
        systemd_state="active"
    )

    mock_systemd.list_services.return_value = [
        SystemdService(name="nginx.service", state="inactive", description="Web Server")
    ]
    mock_systemd.get_service_pid.return_value = None
    mock_db.query.return_value.filter.return_value.first.return_value = existing_service

    # Execute
    result = registry.scan_services()

    # Assert - should update systemd_state
    assert result["updated"] == 1
    assert existing_service.systemd_state == "inactive"
    mock_db.commit.assert_called()


def test_get_configured_services(registry, mock_db):
    """Test getting only configured services."""
    services = [
        Service(name="app1", status=ServiceStatus.CONFIGURED, systemd_state="active"),
        Service(name="app2", status=ServiceStatus.CONFIGURED, systemd_state="active"),
    ]
    mock_db.query.return_value.filter.return_value.all.return_value = services

    result = registry.get_configured_services()

    assert len(result) == 2
    mock_db.query.assert_called()

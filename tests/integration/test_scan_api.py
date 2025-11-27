"""Integration tests for scan API."""
import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from src.api.main import app
from src.models.base import Base, engine
from src.services.systemd_discovery import SystemdService
from src.services.port_detection import PortInfo


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


@patch('src.services.systemd_discovery.SystemdDiscovery.list_services')
@patch('src.services.systemd_discovery.SystemdDiscovery.get_service_pid')
@patch('src.services.port_detection.PortDetection.get_listening_ports')
def test_scan_services(mock_ports, mock_pid, mock_list, client):
    """Test scanning for services."""
    # Setup mocks
    mock_list.return_value = [
        SystemdService(name="nginx.service", state="active", description="Web Server"),
        SystemdService(name="ssh.service", state="active", description="SSH Server"),
    ]
    mock_pid.side_effect = [1234, 5678]
    mock_ports.return_value = [
        PortInfo(port=80, pid=1234),
        PortInfo(port=22, pid=5678),
    ]

    response = client.post("/api/scan")

    assert response.status_code == 200
    data = response.json()
    assert data["total_scanned"] == 2
    assert data["new_discovered"] >= 1  # nginx should be discovered
    assert "stats" in data


@patch('src.services.systemd_discovery.SystemdDiscovery.list_services')
def test_scan_services_error_handling(mock_list, client):
    """Test scan error handling."""
    mock_list.side_effect = Exception("Systemd error")

    response = client.post("/api/scan")

    assert response.status_code == 500
    assert "detail" in response.json()
    assert "Systemd error" in response.json()["detail"]

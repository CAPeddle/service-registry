"""Tests for systemd discovery service."""
import pytest
from unittest.mock import patch, MagicMock
from src.services.systemd_discovery import SystemdDiscovery, SystemdService


@pytest.fixture
def discovery():
    """Create SystemdDiscovery instance."""
    return SystemdDiscovery()


def test_parse_systemctl_list_output(discovery):
    """Test parsing systemctl list-units output."""
    output = """  nginx.service      loaded active running   A high performance web server
  ssh.service        loaded active running   OpenBSD Secure Shell server
  myapp.service      loaded active running   My Application
"""
    services = discovery._parse_systemctl_list(output)

    assert len(services) == 3
    assert services[0].name == "nginx.service"
    assert services[0].state == "active"
    assert services[1].name == "ssh.service"
    assert services[2].name == "myapp.service"


@patch('subprocess.run')
def test_list_services_calls_systemctl(mock_run, discovery):
    """Test that list_services calls systemctl command."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="  test.service       loaded active running   Test Service\n"
    )

    services = discovery.list_services()

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "systemctl" in args
    assert "list-units" in args
    assert "--type=service" in args
    assert len(services) == 1
    assert services[0].name == "test.service"


@patch('subprocess.run')
def test_get_service_pid(mock_run, discovery):
    """Test getting PID for a service."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="MainPID=1234\n"
    )

    pid = discovery.get_service_pid("nginx.service")

    assert pid == 1234
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "systemctl" in args
    assert "show" in args
    assert "nginx.service" in args


@patch('subprocess.run')
def test_get_service_pid_returns_none_when_not_found(mock_run, discovery):
    """Test that get_service_pid returns None when PID not found."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="MainPID=0\n"
    )

    pid = discovery.get_service_pid("stopped.service")

    assert pid is None

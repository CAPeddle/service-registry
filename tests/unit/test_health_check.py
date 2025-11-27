"""Tests for health check service."""
import pytest
from unittest.mock import Mock, patch
import httpx
from src.services.health_check import HealthCheckService, HealthStatus


@pytest.fixture
def health_checker():
    """Create health check service."""
    return HealthCheckService(timeout=2.0, cache_ttl=60)


@patch('httpx.get')
def test_check_health_success(mock_get, health_checker):
    """Test successful health check."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    status = health_checker.check_health("http://localhost:8080/health")

    assert status.is_healthy is True
    assert status.status_code == 200
    mock_get.assert_called_once_with("http://localhost:8080/health", timeout=2.0)


@patch('httpx.get')
def test_check_health_non_200_response(mock_get, health_checker):
    """Test health check with non-200 response."""
    mock_response = Mock()
    mock_response.status_code = 503
    mock_get.return_value = mock_response

    status = health_checker.check_health("http://localhost:8080/health")

    assert status.is_healthy is False
    assert status.status_code == 503


@patch('httpx.get')
def test_check_health_timeout(mock_get, health_checker):
    """Test health check with timeout."""
    mock_get.side_effect = httpx.TimeoutException("Timeout")

    status = health_checker.check_health("http://localhost:8080/health")

    assert status.is_healthy is False
    assert status.status_code is None
    assert status.error == "Timeout"


@patch('httpx.get')
def test_check_health_connection_error(mock_get, health_checker):
    """Test health check with connection error."""
    mock_get.side_effect = httpx.ConnectError("Connection refused")

    status = health_checker.check_health("http://localhost:8080/health")

    assert status.is_healthy is False
    assert status.error == "Connection refused"


def test_build_health_url():
    """Test building health check URL."""
    checker = HealthCheckService()

    url = checker.build_health_url("http://localhost:8080", "/health")
    assert url == "http://localhost:8080/health"

    url = checker.build_health_url("http://localhost:8080/", "/health")
    assert url == "http://localhost:8080/health"

    url = checker.build_health_url("http://localhost:8080", None)
    assert url is None

"""Tests for port detection service."""
import pytest
from unittest.mock import patch, MagicMock
from src.services.port_detection import PortDetection, PortInfo


@pytest.fixture
def detector():
    """Create PortDetection instance."""
    return PortDetection()


def test_parse_ss_output(detector):
    """Test parsing ss -tlnp output."""
    output = """tcp   LISTEN 0      128        0.0.0.0:80        0.0.0.0:*    users:(("nginx",pid=1234,fd=6))
tcp   LISTEN 0      128        0.0.0.0:8080      0.0.0.0:*    users:(("myapp",pid=5678,fd=3))
tcp   LISTEN 0      128           [::]:443          [::]:*    users:(("nginx",pid=1234,fd=7))
"""

    ports = detector._parse_ss_output(output)

    assert len(ports) == 3
    assert ports[0].port == 80
    assert ports[0].pid == 1234
    assert ports[1].port == 8080
    assert ports[1].pid == 5678
    assert ports[2].port == 443


def test_is_web_port(detector):
    """Test web port detection logic."""
    assert detector.is_web_port(80) is True
    assert detector.is_web_port(443) is True
    assert detector.is_web_port(8080) is True
    assert detector.is_web_port(3000) is True
    assert detector.is_web_port(9999) is True
    assert detector.is_web_port(22) is False
    assert detector.is_web_port(2999) is False
    assert detector.is_web_port(10000) is False


@patch('subprocess.run')
def test_get_listening_ports(mock_run, detector):
    """Test getting listening ports."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='tcp   LISTEN 0      128        0.0.0.0:8080      0.0.0.0:*    users:(("app",pid=1234,fd=3))\n'
    )

    ports = detector.get_listening_ports()

    assert len(ports) == 1
    assert ports[0].port == 8080
    assert ports[0].pid == 1234
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "ss" in args
    assert "-tlnp" in args


def test_get_ports_for_pid(detector):
    """Test filtering ports by PID."""
    ports = [
        PortInfo(port=80, pid=1234),
        PortInfo(port=443, pid=1234),
        PortInfo(port=8080, pid=5678),
    ]

    filtered = detector.get_ports_for_pid(ports, 1234)

    assert len(filtered) == 2
    assert filtered[0].port == 80
    assert filtered[1].port == 443

# Service Registry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a web-based service registry that discovers Ubuntu systemd services, detects web services via port scanning, and provides a dashboard for quick access with health monitoring.

**Architecture:** Three-layer architecture with Discovery (systemd integration), Data (SQLite via SQLAlchemy), and API+Frontend (FastAPI with Jinja2 templates). Services are categorized as raw/discovered/configured based on auto-detection and user input.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, Jinja2, httpx, subprocess (for systemd), pytest

---

## Task 1: Database Models and Schema

**Files:**
- Create: `src/models/service.py`
- Modify: `src/models/__init__.py`
- Test: `tests/unit/test_service_model.py`

**Step 1: Write the failing test**

Create `tests/unit/test_service_model.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_service_model.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.models.service'"

**Step 3: Write minimal implementation**

Create `src/models/service.py`:

```python
"""Service model for database."""
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum
from src.models.base import Base


class ServiceStatus(str, Enum):
    """Service status enumeration."""
    RAW = "raw"  # Found in systemd, not a web service
    DISCOVERED = "discovered"  # Auto-detected web service, not configured
    CONFIGURED = "configured"  # User has configured with details


class Service(Base):
    """Service model representing a systemd service."""

    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    port = Column(Integer, nullable=True)
    health_endpoint = Column(String, nullable=True)
    base_url = Column(String, nullable=True)
    status = Column(SQLEnum(ServiceStatus), nullable=False)
    systemd_state = Column(String, nullable=False)
    last_scanned_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

Update `src/models/__init__.py`:

```python
"""Models package."""
from src.models.base import Base, get_db
from src.models.service import Service, ServiceStatus

__all__ = ["Base", "get_db", "Service", "ServiceStatus"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_service_model.py -v`

Expected: PASS (all 3 tests)

**Step 5: Commit**

```bash
git add src/models/service.py src/models/__init__.py tests/unit/test_service_model.py
git commit -m "feat: add Service model with status enum and database schema"
```

---

## Task 2: Systemd Discovery Service

**Files:**
- Create: `src/services/systemd_discovery.py`
- Test: `tests/unit/test_systemd_discovery.py`

**Step 1: Write the failing test**

Create `tests/unit/test_systemd_discovery.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_systemd_discovery.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.services.systemd_discovery'"

**Step 3: Write minimal implementation**

Create `src/services/systemd_discovery.py`:

```python
"""Systemd service discovery."""
import subprocess
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SystemdService:
    """Systemd service information."""
    name: str
    state: str
    description: str = ""


class SystemdDiscovery:
    """Service for discovering systemd services."""

    def list_services(self) -> List[SystemdService]:
        """List all systemd services.

        Returns:
            List of SystemdService objects
        """
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain"],
            capture_output=True,
            text=True,
            check=True
        )
        return self._parse_systemctl_list(result.stdout)

    def _parse_systemctl_list(self, output: str) -> List[SystemdService]:
        """Parse systemctl list-units output.

        Args:
            output: Raw output from systemctl list-units

        Returns:
            List of SystemdService objects
        """
        services = []
        for line in output.strip().split('\n'):
            if not line.strip():
                continue

            # Parse format: "  service.service    loaded active running   Description"
            parts = line.split()
            if len(parts) >= 4:
                name = parts[0]
                state = parts[2]  # active/inactive/failed
                description = ' '.join(parts[4:]) if len(parts) > 4 else ""
                services.append(SystemdService(name=name, state=state, description=description))

        return services

    def get_service_pid(self, service_name: str) -> Optional[int]:
        """Get the main PID for a service.

        Args:
            service_name: Name of the systemd service

        Returns:
            PID as integer, or None if not running
        """
        result = subprocess.run(
            ["systemctl", "show", service_name, "--property=MainPID"],
            capture_output=True,
            text=True,
            check=True
        )

        match = re.search(r'MainPID=(\d+)', result.stdout)
        if match:
            pid = int(match.group(1))
            return pid if pid > 0 else None

        return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_systemd_discovery.py -v`

Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
git add src/services/systemd_discovery.py tests/unit/test_systemd_discovery.py
git commit -m "feat: add systemd service discovery with PID extraction"
```

---

## Task 3: Port Detection Service

**Files:**
- Create: `src/services/port_detection.py`
- Test: `tests/unit/test_port_detection.py`

**Step 1: Write the failing test**

Create `tests/unit/test_port_detection.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_port_detection.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.services.port_detection'"

**Step 3: Write minimal implementation**

Create `src/services/port_detection.py`:

```python
"""Port detection for services."""
import subprocess
import re
from dataclasses import dataclass
from typing import List


@dataclass
class PortInfo:
    """Port information."""
    port: int
    pid: int


class PortDetection:
    """Service for detecting listening ports."""

    # Web service port ranges
    WEB_PORTS = {80, 443}
    WEB_PORT_RANGES = [
        (3000, 3999),
        (4000, 4999),
        (5000, 5999),
        (8000, 8999),
    ]

    def get_listening_ports(self) -> List[PortInfo]:
        """Get all listening TCP ports with their PIDs.

        Returns:
            List of PortInfo objects
        """
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            check=True
        )
        return self._parse_ss_output(result.stdout)

    def _parse_ss_output(self, output: str) -> List[PortInfo]:
        """Parse ss -tlnp output.

        Args:
            output: Raw output from ss command

        Returns:
            List of PortInfo objects
        """
        ports = []
        for line in output.strip().split('\n'):
            # Match pattern like: tcp   LISTEN 0   128   0.0.0.0:80   0.0.0.0:*   users:(("nginx",pid=1234,fd=6))
            port_match = re.search(r':(\d+)\s+', line)
            pid_match = re.search(r'pid=(\d+)', line)

            if port_match and pid_match:
                port = int(port_match.group(1))
                pid = int(pid_match.group(1))
                ports.append(PortInfo(port=port, pid=pid))

        return ports

    def is_web_port(self, port: int) -> bool:
        """Check if a port is typically used for web services.

        Args:
            port: Port number to check

        Returns:
            True if port is in web service range
        """
        if port in self.WEB_PORTS:
            return True

        for start, end in self.WEB_PORT_RANGES:
            if start <= port <= end:
                return True

        return False

    def get_ports_for_pid(self, ports: List[PortInfo], pid: int) -> List[PortInfo]:
        """Filter ports for a specific PID.

        Args:
            ports: List of all port info
            pid: Process ID to filter by

        Returns:
            List of PortInfo for the specified PID
        """
        return [p for p in ports if p.pid == pid]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_port_detection.py -v`

Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add src/services/port_detection.py tests/unit/test_port_detection.py
git commit -m "feat: add port detection service with web port filtering"
```

---

## Task 4: Service Registry Service (Business Logic)

**Files:**
- Create: `src/services/registry_service.py`
- Test: `tests/unit/test_registry_service.py`

**Step 1: Write the failing test**

Create `tests/unit/test_registry_service.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_registry_service.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.services.registry_service'"

**Step 3: Write minimal implementation**

Create `src/services/registry_service.py`:

```python
"""Service registry business logic."""
from datetime import datetime
from typing import List, Dict
from sqlalchemy.orm import Session
from src.models.service import Service, ServiceStatus
from src.services.systemd_discovery import SystemdDiscovery
from src.services.port_detection import PortDetection


class RegistryService:
    """Business logic for service registry."""

    def __init__(
        self,
        db: Session,
        systemd_discovery: SystemdDiscovery,
        port_detector: PortDetection
    ):
        """Initialize registry service.

        Args:
            db: Database session
            systemd_discovery: Systemd discovery service
            port_detector: Port detection service
        """
        self.db = db
        self.systemd = systemd_discovery
        self.port_detector = port_detector

    def scan_services(self) -> Dict[str, int]:
        """Scan systemd for services and update database.

        Returns:
            Dictionary with scan statistics
        """
        stats = {
            "total_scanned": 0,
            "new_discovered": 0,
            "updated": 0,
            "new_raw": 0
        }

        # Get all systemd services
        systemd_services = self.systemd.list_services()
        stats["total_scanned"] = len(systemd_services)

        # Get all listening ports
        listening_ports = self.port_detector.get_listening_ports()

        for svc in systemd_services:
            # Check if service already exists
            existing = self.db.query(Service).filter(Service.name == svc.name).first()

            if existing:
                # Update systemd state
                existing.systemd_state = svc.state
                existing.last_scanned_at = datetime.utcnow()
                stats["updated"] += 1
            else:
                # Get PID and check for listening ports
                pid = self.systemd.get_service_pid(svc.name)
                port = None
                status = ServiceStatus.RAW

                if pid:
                    service_ports = self.port_detector.get_ports_for_pid(listening_ports, pid)
                    web_ports = [p for p in service_ports if self.port_detector.is_web_port(p.port)]

                    if web_ports:
                        port = web_ports[0].port
                        status = ServiceStatus.DISCOVERED
                        stats["new_discovered"] += 1
                    else:
                        stats["new_raw"] += 1
                else:
                    stats["new_raw"] += 1

                # Create new service
                new_service = Service(
                    name=svc.name,
                    description=svc.description if status == ServiceStatus.DISCOVERED else None,
                    port=port,
                    status=status,
                    systemd_state=svc.state,
                    last_scanned_at=datetime.utcnow()
                )
                self.db.add(new_service)

        self.db.commit()
        return stats

    def get_configured_services(self) -> List[Service]:
        """Get all configured services.

        Returns:
            List of configured services
        """
        return self.db.query(Service).filter(
            Service.status == ServiceStatus.CONFIGURED
        ).all()

    def get_discovered_services(self) -> List[Service]:
        """Get all discovered but not configured services.

        Returns:
            List of discovered services
        """
        return self.db.query(Service).filter(
            Service.status == ServiceStatus.DISCOVERED
        ).all()

    def get_all_services(self) -> List[Service]:
        """Get all services from database.

        Returns:
            List of all services
        """
        return self.db.query(Service).all()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_registry_service.py -v`

Expected: PASS (all 3 tests)

**Step 5: Commit**

```bash
git add src/services/registry_service.py tests/unit/test_registry_service.py
git commit -m "feat: add registry service with scan and query logic"
```

---

## Task 5: Health Check Service

**Files:**
- Create: `src/services/health_check.py`
- Test: `tests/unit/test_health_check.py`

**Step 1: Write the failing test**

Create `tests/unit/test_health_check.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_health_check.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.services.health_check'"

**Step 3: Write minimal implementation**

Create `src/services/health_check.py`:

```python
"""Health check service for monitoring service health."""
import httpx
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta


@dataclass
class HealthStatus:
    """Health check result."""
    is_healthy: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    checked_at: datetime = None

    def __post_init__(self):
        if self.checked_at is None:
            self.checked_at = datetime.utcnow()


class HealthCheckService:
    """Service for checking health of registered services."""

    def __init__(self, timeout: float = 2.0, cache_ttl: int = 60):
        """Initialize health check service.

        Args:
            timeout: Request timeout in seconds
            cache_ttl: Cache time-to-live in seconds
        """
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: dict[str, HealthStatus] = {}

    def check_health(self, url: str, use_cache: bool = True) -> HealthStatus:
        """Check health of a service endpoint.

        Args:
            url: Full URL to health endpoint
            use_cache: Whether to use cached result if available

        Returns:
            HealthStatus object with results
        """
        # Check cache
        if use_cache and url in self._cache:
            cached = self._cache[url]
            if datetime.utcnow() - cached.checked_at < timedelta(seconds=self.cache_ttl):
                return cached

        # Perform health check
        try:
            response = httpx.get(url, timeout=self.timeout)
            status = HealthStatus(
                is_healthy=response.status_code == 200,
                status_code=response.status_code
            )
        except httpx.TimeoutException:
            status = HealthStatus(is_healthy=False, error="Timeout")
        except httpx.ConnectError as e:
            status = HealthStatus(is_healthy=False, error=str(e))
        except Exception as e:
            status = HealthStatus(is_healthy=False, error=f"Error: {str(e)}")

        # Cache result
        self._cache[url] = status
        return status

    def build_health_url(self, base_url: str, health_endpoint: Optional[str]) -> Optional[str]:
        """Build full health check URL.

        Args:
            base_url: Base URL of service
            health_endpoint: Health endpoint path

        Returns:
            Full URL or None if health_endpoint is None
        """
        if health_endpoint is None:
            return None

        base = base_url.rstrip('/')
        endpoint = health_endpoint if health_endpoint.startswith('/') else f'/{health_endpoint}'
        return f"{base}{endpoint}"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_health_check.py -v`

Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add src/services/health_check.py tests/unit/test_health_check.py
git commit -m "feat: add health check service with caching"
```

---

## Task 6: API Schemas (Pydantic Models)

**Files:**
- Create: `src/api/schemas/service_schema.py`
- Modify: `src/api/schemas/__init__.py`
- Test: `tests/unit/test_service_schema.py`

**Step 1: Write the failing test**

Create `tests/unit/test_service_schema.py`:

```python
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
    from datetime import datetime

    service = Service(
        id=1,
        name="test.service",
        description="Test Service",
        port=8080,
        base_url="http://localhost:8080",
        health_endpoint="/health",
        status=ServiceStatus.CONFIGURED,
        systemd_state="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    schema = ServiceResponse.model_validate(service)

    assert schema.id == 1
    assert schema.name == "test.service"
    assert schema.status == ServiceStatus.CONFIGURED
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_service_schema.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.api.schemas.service_schema'"

**Step 3: Write minimal implementation**

Create `src/api/schemas/service_schema.py`:

```python
"""Pydantic schemas for service API."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator
from src.models.service import ServiceStatus


class ServiceBase(BaseModel):
    """Base service schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    health_endpoint: Optional[str] = None
    base_url: Optional[str] = None


class ServiceCreate(ServiceBase):
    """Schema for creating a service."""
    description: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)

    @field_validator('base_url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v

    @field_validator('health_endpoint')
    @classmethod
    def validate_health_endpoint(cls, v: Optional[str]) -> Optional[str]:
        """Validate health endpoint format."""
        if v is not None and not v.startswith('/'):
            raise ValueError('Health endpoint must start with /')
        return v


class ServiceUpdate(BaseModel):
    """Schema for updating a service."""
    description: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    health_endpoint: Optional[str] = None
    base_url: Optional[str] = None

    @field_validator('base_url')
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate URL format."""
        if v is not None and not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v


class ServiceResponse(ServiceBase):
    """Schema for service response."""
    id: int
    status: ServiceStatus
    systemd_state: str
    last_scanned_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

Update `src/api/schemas/__init__.py`:

```python
"""API schemas package."""
from src.api.schemas.service_schema import ServiceCreate, ServiceUpdate, ServiceResponse

__all__ = ["ServiceCreate", "ServiceUpdate", "ServiceResponse"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_service_schema.py -v`

Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add src/api/schemas/service_schema.py src/api/schemas/__init__.py tests/unit/test_service_schema.py
git commit -m "feat: add Pydantic schemas for service API with validation"
```

---

## Task 7: Service API Endpoints

**Files:**
- Create: `src/api/routes/services.py`
- Modify: `src/api/main.py`
- Test: `tests/integration/test_services_api.py`

**Step 1: Write the failing test**

Create `tests/integration/test_services_api.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_services_api.py -v`

Expected: FAIL with "404 Not Found" for /api/services

**Step 3: Write minimal implementation**

Create `src/api/routes/services.py`:

```python
"""Service management API routes."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.models.base import get_db
from src.models.service import Service, ServiceStatus
from src.api.schemas.service_schema import ServiceCreate, ServiceUpdate, ServiceResponse


router = APIRouter()


@router.get("", response_model=List[ServiceResponse])
def list_services(db: Session = Depends(get_db)):
    """List all services."""
    services = db.query(Service).all()
    return services


@router.get("/{service_id}", response_model=ServiceResponse)
def get_service(service_id: int, db: Session = Depends(get_db)):
    """Get a service by ID."""
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
def create_service(service_data: ServiceCreate, db: Session = Depends(get_db)):
    """Create a new service."""
    # Check if service already exists
    existing = db.query(Service).filter(Service.name == service_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Service already exists")

    # Create service
    service = Service(
        name=service_data.name,
        description=service_data.description,
        port=service_data.port,
        health_endpoint=service_data.health_endpoint,
        base_url=service_data.base_url,
        status=ServiceStatus.CONFIGURED,
        systemd_state="unknown"
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.put("/{service_id}", response_model=ServiceResponse)
def update_service(
    service_id: int,
    service_data: ServiceUpdate,
    db: Session = Depends(get_db)
):
    """Update a service."""
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # Update fields
    update_data = service_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)

    db.commit()
    db.refresh(service)
    return service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(service_id: int, db: Session = Depends(get_db)):
    """Delete a service."""
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    db.delete(service)
    db.commit()
```

Update `src/api/main.py` to include the services router:

```python
"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.api.routes import health, services

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
app.include_router(services.router, prefix="/api/services", tags=["services"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.version,
        "docs": "/docs"
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_services_api.py -v`

Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add src/api/routes/services.py src/api/main.py tests/integration/test_services_api.py
git commit -m "feat: add REST API endpoints for service management"
```

---

## Task 8: Scan API Endpoint

**Files:**
- Create: `src/api/routes/scan.py`
- Modify: `src/api/main.py`
- Create: `src/api/dependencies/services.py`
- Test: `tests/integration/test_scan_api.py`

**Step 1: Write the failing test**

Create `tests/integration/test_scan_api.py`:

```python
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
    assert "error" in response.json()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_scan_api.py -v`

Expected: FAIL with "404 Not Found" for /api/scan

**Step 3: Write minimal implementation**

Create `src/api/dependencies/services.py`:

```python
"""Dependency injection for services."""
from fastapi import Depends
from sqlalchemy.orm import Session
from src.models.base import get_db
from src.services.systemd_discovery import SystemdDiscovery
from src.services.port_detection import PortDetection
from src.services.registry_service import RegistryService


def get_systemd_discovery() -> SystemdDiscovery:
    """Get systemd discovery instance."""
    return SystemdDiscovery()


def get_port_detector() -> PortDetection:
    """Get port detection instance."""
    return PortDetection()


def get_registry_service(
    db: Session = Depends(get_db),
    systemd: SystemdDiscovery = Depends(get_systemd_discovery),
    port_detector: PortDetection = Depends(get_port_detector)
) -> RegistryService:
    """Get registry service instance."""
    return RegistryService(db, systemd, port_detector)
```

Create `src/api/routes/scan.py`:

```python
"""Scan API routes."""
from fastapi import APIRouter, Depends, HTTPException
from src.services.registry_service import RegistryService
from src.api.dependencies.services import get_registry_service


router = APIRouter()


@router.post("")
def scan_services(registry: RegistryService = Depends(get_registry_service)):
    """Scan systemd for services and update database.

    Returns:
        Scan statistics including total scanned and new discoveries
    """
    try:
        stats = registry.scan_services()
        return {
            "message": "Scan completed successfully",
            "stats": stats,
            **stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")
```

Update `src/api/main.py`:

```python
"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.api.routes import health, services, scan

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
app.include_router(services.router, prefix="/api/services", tags=["services"])
app.include_router(scan.router, prefix="/api/scan", tags=["scan"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.version,
        "docs": "/docs"
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_scan_api.py -v`

Expected: PASS (all 2 tests)

**Step 5: Commit**

```bash
git add src/api/routes/scan.py src/api/dependencies/services.py src/api/main.py tests/integration/test_scan_api.py
git commit -m "feat: add scan API endpoint with systemd integration"
```

---

## Task 9: HTML Templates - Landing Page

**Files:**
- Create: `src/api/templates/base.html`
- Create: `src/api/templates/index.html`
- Create: `src/api/routes/pages.py`
- Modify: `src/api/main.py`

**Step 1: Create base template**

Create `src/api/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Service Registry{% endblock %}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
            background: #f5f5f5;
        }
        header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 { color: #333; font-size: 24px; }
        .btn {
            background: #007bff;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }
        .btn:hover { background: #0056b3; }
        main {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
            color: #495057;
        }
        .status {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status.healthy { background: #28a745; }
        .status.unhealthy { background: #dc3545; }
        .status.unknown { background: #6c757d; }
        .service-link {
            color: #007bff;
            text-decoration: none;
            font-weight: 500;
        }
        .service-link:hover { text-decoration: underline; }
        .actions a {
            margin-right: 10px;
            color: #007bff;
            text-decoration: none;
            font-size: 14px;
        }
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #6c757d;
        }
    </style>
    {% block extra_head %}{% endblock %}
</head>
<body>
    <header>
        <h1>{% block header %}Service Registry{% endblock %}</h1>
        {% block header_actions %}{% endblock %}
    </header>
    <main>
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

**Step 2: Create index template**

Create `src/api/templates/index.html`:

```html
{% extends "base.html" %}

{% block header_actions %}
<a href="/scan" class="btn">Scan for Services</a>
{% endblock %}

{% block content %}
{% if services %}
<table>
    <thead>
        <tr>
            <th>Service Name</th>
            <th>Status</th>
            <th>Description</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        {% for service in services %}
        <tr>
            <td>
                <a href="{{ service.base_url }}" target="_blank" class="service-link">
                    {{ service.name }}
                </a>
            </td>
            <td>
                <span class="status {{ service.health_status }}"></span>
                {{ service.health_status }}
            </td>
            <td>{{ service.description or '-' }}</td>
            <td class="actions">
                <a href="{{ service.base_url }}" target="_blank">Visit</a>
                {% if service.health_url %}
                <a href="{{ service.health_url }}" target="_blank">Health</a>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% else %}
<div class="empty-state">
    <p>No configured services found.</p>
    <p>Click "Scan for Services" to discover services on this server.</p>
</div>
{% endif %}
{% endblock %}
```

**Step 3: Create pages router**

Create `src/api/routes/pages.py`:

```python
"""HTML page routes."""
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from src.services.registry_service import RegistryService
from src.services.health_check import HealthCheckService
from src.api.dependencies.services import get_registry_service


router = APIRouter()
templates = Jinja2Templates(directory="src/api/templates")


@router.get("/")
def index(
    request: Request,
    registry: RegistryService = Depends(get_registry_service)
):
    """Landing page showing configured services."""
    services = registry.get_configured_services()
    health_checker = HealthCheckService()

    # Enrich services with health status
    service_data = []
    for service in services:
        health_url = health_checker.build_health_url(service.base_url, service.health_endpoint)

        if health_url:
            health = health_checker.check_health(health_url)
            health_status = "healthy" if health.is_healthy else "unhealthy"
        else:
            health_status = "unknown"

        service_data.append({
            "name": service.name,
            "description": service.description,
            "base_url": service.base_url,
            "health_url": health_url,
            "health_status": health_status
        })

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "services": service_data}
    )
```

**Step 4: Update main.py**

Update `src/api/main.py`:

```python
"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.api.routes import health, services, scan, pages

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
app.include_router(services.router, prefix="/api/services", tags=["services"])
app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
app.include_router(pages.router, tags=["pages"])
```

**Step 5: Install Jinja2 and test manually**

Run: `pip install jinja2`

Then: `uvicorn src.api.main:app --reload`

Visit: `http://localhost:8000/`

Expected: See landing page (empty state since no services configured)

**Step 6: Commit**

```bash
git add src/api/templates/ src/api/routes/pages.py src/api/main.py
git commit -m "feat: add landing page HTML template with service list"
```

---

## Task 10: HTML Templates - Scan Page

**Files:**
- Create: `src/api/templates/scan.html`
- Modify: `src/api/routes/pages.py`

**Step 1: Create scan page template**

Create `src/api/templates/scan.html`:

```html
{% extends "base.html" %}

{% block title %}Scan Services - Service Registry{% endblock %}

{% block header %}Scan for Services{% endblock %}

{% block header_actions %}
<a href="/" class="btn">Back to Dashboard</a>
{% endblock %}

{% block extra_head %}
<style>
    .section {
        margin-bottom: 30px;
    }
    .section h2 {
        margin-bottom: 15px;
        color: #495057;
        font-size: 18px;
        border-bottom: 2px solid #dee2e6;
        padding-bottom: 8px;
    }
    .configure-btn {
        background: #28a745;
        color: white;
        padding: 6px 12px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        text-decoration: none;
        font-size: 14px;
    }
    .configure-btn:hover {
        background: #218838;
    }
    .modal {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        align-items: center;
        justify-content: center;
    }
    .modal.active {
        display: flex;
    }
    .modal-content {
        background: white;
        padding: 30px;
        border-radius: 8px;
        max-width: 500px;
        width: 90%;
    }
    .form-group {
        margin-bottom: 15px;
    }
    .form-group label {
        display: block;
        margin-bottom: 5px;
        font-weight: 500;
        color: #495057;
    }
    .form-group input, .form-group textarea {
        width: 100%;
        padding: 8px 12px;
        border: 1px solid #ced4da;
        border-radius: 4px;
        font-size: 14px;
    }
    .form-group textarea {
        resize: vertical;
        min-height: 60px;
    }
    .form-actions {
        display: flex;
        gap: 10px;
        justify-content: flex-end;
        margin-top: 20px;
    }
    .btn-secondary {
        background: #6c757d;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
    }
    .btn-secondary:hover {
        background: #5a6268;
    }
    details {
        margin-top: 10px;
    }
    summary {
        cursor: pointer;
        padding: 10px;
        background: #f8f9fa;
        border-radius: 4px;
        font-weight: 500;
    }
    summary:hover {
        background: #e9ecef;
    }
</style>
{% endblock %}

{% block content %}
<div class="section">
    <h2>Discovered Web Services</h2>
    {% if discovered %}
    <table>
        <thead>
            <tr>
                <th>Service Name</th>
                <th>Port</th>
                <th>State</th>
                <th>Action</th>
            </tr>
        </thead>
        <tbody>
            {% for service in discovered %}
            <tr>
                <td>{{ service.name }}</td>
                <td>{{ service.port or '-' }}</td>
                <td>{{ service.systemd_state }}</td>
                <td>
                    <button class="configure-btn" onclick="openConfigModal('{{ service.name }}', {{ service.port or 'null' }})">
                        Configure
                    </button>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p>No new web services discovered. All detected services are already configured.</p>
    {% endif %}
</div>

<div class="section">
    <details>
        <summary>All Systemd Services ({{ all_services|length }})</summary>
        <table>
            <thead>
                <tr>
                    <th>Service Name</th>
                    <th>Status</th>
                    <th>State</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                {% for service in all_services %}
                <tr>
                    <td>{{ service.name }}</td>
                    <td>{{ service.status }}</td>
                    <td>{{ service.systemd_state }}</td>
                    <td>
                        {% if service.status == 'raw' %}
                        <button class="configure-btn" onclick="openConfigModal('{{ service.name }}', null)">
                            Add to Registry
                        </button>
                        {% else %}
                        <span>{{ service.status }}</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </details>
</div>

<!-- Configuration Modal -->
<div id="configModal" class="modal">
    <div class="modal-content">
        <h2>Configure Service</h2>
        <form id="configForm">
            <div class="form-group">
                <label>Service Name</label>
                <input type="text" id="serviceName" readonly>
            </div>
            <div class="form-group">
                <label>Description *</label>
                <textarea id="description" required></textarea>
            </div>
            <div class="form-group">
                <label>Base URL *</label>
                <input type="url" id="baseUrl" placeholder="http://192.168.2.24:8080" required>
            </div>
            <div class="form-group">
                <label>Port</label>
                <input type="number" id="port" min="1" max="65535">
            </div>
            <div class="form-group">
                <label>Health Endpoint</label>
                <input type="text" id="healthEndpoint" placeholder="/health">
            </div>
            <div class="form-actions">
                <button type="button" class="btn-secondary" onclick="closeConfigModal()">Cancel</button>
                <button type="submit" class="btn">Save</button>
            </div>
        </form>
    </div>
</div>

<script>
    function openConfigModal(name, port) {
        document.getElementById('serviceName').value = name;
        document.getElementById('port').value = port || '';
        if (port) {
            document.getElementById('baseUrl').value = `http://192.168.2.24:${port}`;
        }
        document.getElementById('configModal').classList.add('active');
    }

    function closeConfigModal() {
        document.getElementById('configModal').classList.remove('active');
        document.getElementById('configForm').reset();
    }

    document.getElementById('configForm').addEventListener('submit', async (e) => {
        e.preventDefault();

        const data = {
            name: document.getElementById('serviceName').value,
            description: document.getElementById('description').value,
            base_url: document.getElementById('baseUrl').value,
            port: parseInt(document.getElementById('port').value) || null,
            health_endpoint: document.getElementById('healthEndpoint').value || null
        };

        const response = await fetch('/api/services', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            window.location.reload();
        } else {
            alert('Failed to save service');
        }
    });
</script>
{% endblock %}
```

**Step 2: Add scan page route**

Update `src/api/routes/pages.py`:

```python
"""HTML page routes."""
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from src.models.service import ServiceStatus
from src.services.registry_service import RegistryService
from src.services.health_check import HealthCheckService
from src.api.dependencies.services import get_registry_service


router = APIRouter()
templates = Jinja2Templates(directory="src/api/templates")


@router.get("/")
def index(
    request: Request,
    registry: RegistryService = Depends(get_registry_service)
):
    """Landing page showing configured services."""
    services = registry.get_configured_services()
    health_checker = HealthCheckService()

    # Enrich services with health status
    service_data = []
    for service in services:
        health_url = health_checker.build_health_url(service.base_url, service.health_endpoint)

        if health_url:
            health = health_checker.check_health(health_url)
            health_status = "healthy" if health.is_healthy else "unhealthy"
        else:
            health_status = "unknown"

        service_data.append({
            "name": service.name,
            "description": service.description,
            "base_url": service.base_url,
            "health_url": health_url,
            "health_status": health_status
        })

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "services": service_data}
    )


@router.get("/scan")
def scan_page(
    request: Request,
    registry: RegistryService = Depends(get_registry_service)
):
    """Scan page for discovering and configuring services."""
    # Trigger scan
    registry.scan_services()

    # Get discovered and all services
    discovered = registry.get_discovered_services()
    all_services = registry.get_all_services()

    return templates.TemplateResponse(
        "scan.html",
        {
            "request": request,
            "discovered": discovered,
            "all_services": all_services
        }
    )
```

**Step 3: Test manually**

Run: `uvicorn src.api.main:app --reload`

Visit: `http://localhost:8000/scan`

Expected: See scan page with sections for discovered and all services

**Step 4: Commit**

```bash
git add src/api/templates/scan.html src/api/routes/pages.py
git commit -m "feat: add scan page with service discovery and configuration modal"
```

---

## Task 11: Database Initialization

**Files:**
- Create: `src/core/database.py`
- Modify: `src/api/main.py`

**Step 1: Create database initialization**

Create `src/core/database.py`:

```python
"""Database initialization and utilities."""
from src.models.base import Base, engine


def init_db():
    """Initialize database by creating all tables."""
    Base.metadata.create_all(bind=engine)


def drop_db():
    """Drop all database tables."""
    Base.metadata.drop_all(bind=engine)
```

**Step 2: Add startup event to main.py**

Update `src/api/main.py`:

```python
"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.core.database import init_db
from src.api.routes import health, services, scan, pages

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    """Initialize database on startup."""
    init_db()


# Include routers
app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
app.include_router(services.router, prefix="/api/services", tags=["services"])
app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
app.include_router(pages.router, tags=["pages"])
```

**Step 3: Test manually**

Run: `uvicorn src.api.main:app --reload`

Check: `ls -la` should show `app.db` file created

**Step 4: Commit**

```bash
git add src/core/database.py src/api/main.py
git commit -m "feat: add database initialization on app startup"
```

---

## Task 12: Update Configuration

**Files:**
- Modify: `src/config/__init__.py`
- Modify: `.env.example`

**Step 1: Update settings**

Update `src/config/__init__.py`:

```python
"""Application configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Application
    app_name: str = "Service Registry"
    version: str = "0.1.0"
    debug: bool = False

    # API
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "sqlite:///./service_registry.db"

    # Health Check
    health_check_timeout: float = 2.0
    health_check_cache_ttl: int = 60

    class Config:
        """Pydantic config."""
        env_file = ".env"


settings = Settings()
```

**Step 2: Update .env.example**

Update `.env.example`:

```
# Application
APP_NAME=Service Registry
VERSION=0.1.0
DEBUG=false

# Database
DATABASE_URL=sqlite:///./service_registry.db

# Health Checks
HEALTH_CHECK_TIMEOUT=2.0
HEALTH_CHECK_CACHE_TTL=60
```

**Step 3: Commit**

```bash
git add src/config/__init__.py .env.example
git commit -m "chore: update configuration for service registry"
```

---

## Task 13: Update README

**Files:**
- Modify: `README.md`

**Step 1: Write comprehensive README**

Update `README.md`:

```markdown
# Service Registry

A web-based service registry that discovers running services on an Ubuntu server via systemd, intelligently identifies web services, and provides a simple dashboard for quick access with health monitoring.

## Features

- **Auto-discovery**: Automatically scans systemd services and detects web services via port scanning
- **Smart filtering**: Identifies services listening on web ports (80, 443, 3000-9999)
- **Health monitoring**: Checks service health with configurable endpoints
- **Simple UI**: Clean HTML interface for viewing and managing services
- **REST API**: Full API for programmatic access

## Quick Start

### Prerequisites

- Python 3.11+
- Ubuntu/Debian system with systemd
- Root or sudo access (for systemd/port scanning)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd service_registry
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

4. Access the dashboard:
```
http://192.168.2.24:8000
```

## Usage

### Web Interface

1. **Dashboard** (`/`): View all configured services with health status
2. **Scan Page** (`/scan`): Discover new services and configure them

### API Endpoints

- `GET /api/services` - List all services
- `POST /api/services` - Create/configure a service
- `GET /api/services/{id}` - Get service details
- `PUT /api/services/{id}` - Update service
- `DELETE /api/services/{id}` - Delete service
- `POST /api/scan` - Trigger systemd scan

### Service Configuration

When a service is discovered, configure it with:
- **Description**: What the service does
- **Base URL**: Service URL (e.g., `http://192.168.2.24:8080`)
- **Port**: Listening port
- **Health Endpoint**: Optional health check path (e.g., `/health`)

## Architecture

- **Discovery Layer**: Systemd integration via `systemctl` commands
- **Port Detection**: Uses `ss -tlnp` to map services to ports
- **Data Layer**: SQLite database with SQLAlchemy ORM
- **API Layer**: FastAPI REST endpoints
- **Frontend**: Jinja2 HTML templates

## Development

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov

# Specific test file
pytest tests/unit/test_service_model.py -v
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint
flake8 src/ tests/

# Type check
mypy src/
```

## Configuration

Edit `.env` file or set environment variables:

```
APP_NAME=Service Registry
DATABASE_URL=sqlite:///./service_registry.db
HEALTH_CHECK_TIMEOUT=2.0
HEALTH_CHECK_CACHE_TTL=60
```

## License

MIT
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with service registry documentation"
```

---

## Execution Options

Plan complete and saved to `docs/plans/2025-11-26-service-registry-implementation.md`.

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**

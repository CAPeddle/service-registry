"""Service registry business logic."""
from datetime import datetime, UTC
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
                existing.last_scanned_at = datetime.now(UTC)
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
                    last_scanned_at=datetime.now(UTC)
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

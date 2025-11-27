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

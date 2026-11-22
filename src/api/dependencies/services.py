"""Dependency injection for services."""
from fastapi import Depends
from sqlalchemy.orm import Session
from src.models.base import get_db
from src.services.systemd_discovery import SystemdDiscovery
from src.services.port_detection import PortDetection
from src.services.registry_service import RegistryService
from src.services.health_check import HealthCheckService, shared_health_check_service
from src.repositories.annotation_repository import AnnotationRepository
from src.services.discovery.inventory import InventoryService, shared_source_cache


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


def get_health_check_service() -> HealthCheckService:
    """Get the shared health check service (its caches persist across requests)."""
    return shared_health_check_service


def get_inventory_service(db: Session = Depends(get_db)) -> InventoryService:
    """Get an inventory service over the shared source cache and this request's annotations."""
    return InventoryService(shared_source_cache, AnnotationRepository(db))

"""Dependency injection for services."""
from fastapi import Depends
from sqlalchemy.orm import Session
from src.models.base import get_db
from src.services.health_check import HealthCheckService, shared_health_check_service
from src.repositories.annotation_repository import AnnotationRepository
from src.services.discovery.inventory import InventoryService, shared_source_cache


def get_health_check_service() -> HealthCheckService:
    """Get the shared health check service."""
    return shared_health_check_service


def get_inventory_service(db: Session = Depends(get_db)) -> InventoryService:
    """Get an inventory service over the shared source cache and this request's annotations."""
    return InventoryService(shared_source_cache, AnnotationRepository(db))

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

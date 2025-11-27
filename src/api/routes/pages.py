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

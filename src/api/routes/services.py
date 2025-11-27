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

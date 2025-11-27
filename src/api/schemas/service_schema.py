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

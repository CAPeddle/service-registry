"""Pydantic schemas for service API."""
from typing import Optional
from pydantic import BaseModel, Field, field_validator


def _require_http_url(v: str) -> str:
    if not v.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    return v


def _require_leading_slash(v: str, label: str) -> str:
    if not v.startswith("/"):
        raise ValueError(f"{label} must start with /")
    return v


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

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        return _require_http_url(v)

    @field_validator("health_endpoint")
    @classmethod
    def validate_health_endpoint(cls, v: Optional[str]) -> Optional[str]:
        """Validate health endpoint format."""
        return v if v is None else _require_leading_slash(v, "Health endpoint")


def _blank_to_none(v: Optional[str]) -> Optional[str]:
    if v is None or not v.strip():
        return None
    return v.strip()


class AnnotationUpdate(BaseModel):
    """Schema for editing one service's annotation by identity key.

    Fields left out are unchanged. An empty string clears a text field.
    ``hidden`` null returns the row to its default visibility.
    """

    identity_key: str = Field(..., min_length=1, max_length=512)
    display_name: Optional[str] = None
    description: Optional[str] = None
    hidden: Optional[bool] = None
    link_override: Optional[str] = None
    health_path: Optional[str] = None
    primary_port: Optional[int] = Field(None, ge=1, le=65535)

    @field_validator("display_name", "description")
    @classmethod
    def blank_text_clears(cls, v: Optional[str]) -> Optional[str]:
        return _blank_to_none(v)

    @field_validator("link_override")
    @classmethod
    def validate_link(cls, v: Optional[str]) -> Optional[str]:
        v = _blank_to_none(v)
        return v if v is None else _require_http_url(v)

    @field_validator("health_path")
    @classmethod
    def validate_health_path(cls, v: Optional[str]) -> Optional[str]:
        v = _blank_to_none(v)
        return v if v is None else _require_leading_slash(v, "Health path")


class AnnotationResponse(BaseModel):
    """Schema for an annotation."""

    identity_key: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    hidden: Optional[bool] = None
    link_override: Optional[str] = None
    health_path: Optional[str] = None
    primary_port: Optional[int] = None

    model_config = {"from_attributes": True}

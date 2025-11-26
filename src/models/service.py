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

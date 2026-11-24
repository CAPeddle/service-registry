"""A registration whose values were held back because a page edit protects them."""
from datetime import datetime, UTC
from sqlalchemy import JSON, Column, DateTime, Integer, String
from src.models.base import Base

# Annotation fields a page edit protects, and the attribute holding each one's posted value.
PROTECTED_FIELDS = {"description": "description", "health_path": "health_endpoint"}


class RegistrationAttempt(Base):
    """The values a POST registration carried, kept for review on the landing page."""

    __tablename__ = "registration_attempts"
    # Never reuse an id, so a button on a stale page cannot act on a newer registration.
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True, index=True)
    identity_key = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    base_url = Column(String, nullable=True)
    health_endpoint = Column(String, nullable=True)
    held_fields = Column(JSON, nullable=False)  # annotation field names, e.g. ["description"]
    received_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

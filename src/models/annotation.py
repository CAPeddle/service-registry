"""Annotation model: the user's per-service choices, keyed by stable identity."""
from datetime import datetime, UTC
from sqlalchemy import Column, Integer, String, Boolean, DateTime, false
from src.models.base import Base


class Annotation(Base):
    """User-supplied details for one discovered or manual service."""

    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)
    identity_key = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    description = Column(String, nullable=True)
    hidden = Column(Boolean, nullable=True, default=None)
    link_override = Column(String, nullable=True)
    health_path = Column(String, nullable=True)
    primary_port = Column(Integer, nullable=True)
    # Set by page edits; a registration does not overwrite a field the page set.
    description_from_page = Column(Boolean, nullable=False, default=False, server_default=false())
    health_path_from_page = Column(Boolean, nullable=False, default=False, server_default=false())
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

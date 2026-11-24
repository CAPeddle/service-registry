"""Database initialization and utilities."""
import pwd
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from src.models.base import Base, engine as default_engine

USER_UID = 1000
# SQLite's user_version once the old services table has been imported.
IMPORTED_VERSION = 1
# The service runs as root, so look in the household user's home, not root's.
_USER_UNIT_DIRS = (
    Path(pwd.getpwuid(USER_UID).pw_dir) / ".config" / "systemd" / "user",
    Path("/etc/systemd/user"),
    Path("/usr/lib/systemd/user"),
)


def user_unit_exists(name: str) -> bool:
    """Return True if a systemd user unit with this name is installed."""
    return any((d / name).is_file() for d in _USER_UNIT_DIRS)


def import_configured_services(engine: Engine, unit_exists: Callable[[str], bool]) -> None:
    """Copy CONFIGURED rows of the old services table into annotations, once.

    The database records that this has run, so deleted annotations stay deleted.
    Annotations written before that record existed also mean it has run.
    """
    inspector = inspect(engine)
    if not inspector.has_table("services"):
        return
    with engine.begin() as conn:
        if conn.execute(text("PRAGMA user_version")).scalar() >= IMPORTED_VERSION:
            return
        if conn.execute(text("SELECT COUNT(*) FROM annotations")).scalar():
            conn.execute(text(f"PRAGMA user_version = {IMPORTED_VERSION}"))
            return
        rows = conn.execute(
            text(
                "SELECT name, description, health_endpoint, base_url, systemd_state FROM services "
                "WHERE status = 'CONFIGURED'"
            )
        ).all()
        for name, description, health, base_url, systemd_state in rows:
            link = None
            if systemd_state != "unknown":
                key = f"system:{name}"
            elif unit_exists(name):
                key = f"user:{USER_UID}:{name}"
            else:
                key = f"manual:{name}"
                # Nothing is discovered for a manual row, so its stored link is the only one.
                if base_url and base_url.startswith(("http://", "https://")):
                    link = base_url
            conn.execute(
                text(
                    "INSERT INTO annotations (identity_key, description, health_path, "
                    "link_override, hidden, "
                    "created_at, updated_at) "
                    "VALUES (:key, :description, :health, :link, NULL, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"key": key, "description": description, "health": health, "link": link},
            )
        conn.execute(text(f"PRAGMA user_version = {IMPORTED_VERSION}"))


def init_db(
    engine: Optional[Engine] = None, user_unit_exists: Callable[[str], bool] = user_unit_exists
):
    """Initialize database by creating all tables and importing old entries."""
    engine = engine or default_engine
    Base.metadata.create_all(bind=engine)
    add_missing_annotation_columns(engine)
    import_configured_services(engine, user_unit_exists)


# Columns added to annotations after its first release; create_all does not add them.
_ADDED_ANNOTATION_COLUMNS = ("description_from_page", "health_path_from_page")


def add_missing_annotation_columns(engine: Engine) -> None:
    """Add columns that an annotations table created by an earlier build lacks."""
    existing = {column["name"] for column in inspect(engine).get_columns("annotations")}
    with engine.begin() as conn:
        for name in _ADDED_ANNOTATION_COLUMNS:
            if name not in existing:
                conn.execute(
                    text(f"ALTER TABLE annotations ADD COLUMN {name} BOOLEAN NOT NULL DEFAULT 0")
                )


def drop_db():
    """Drop all database tables."""
    Base.metadata.drop_all(bind=default_engine)

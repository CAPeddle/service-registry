"""Guard: the test suite must never touch a real service_registry.db."""
from pathlib import Path

from src.config import settings
from src.models.base import engine

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_DB = Path("/home/cpeddle/service-registry/service_registry.db")


def _engine_db_path() -> Path:
    database = engine.url.database
    assert database, "tests must use a file-backed or in-memory SQLite database"
    return Path(database).resolve()


def test_settings_do_not_point_at_a_real_database():
    assert settings.database_url != "sqlite:///./service_registry.db"


def test_engine_is_not_bound_to_repo_or_live_database():
    path = _engine_db_path()
    assert path != (REPO_ROOT / "service_registry.db").resolve()
    assert path != LIVE_DB.resolve()
    assert path.name != "service_registry.db"

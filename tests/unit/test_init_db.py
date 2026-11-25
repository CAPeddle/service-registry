"""init_db brings a database created by an earlier build up to the current schema."""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import src.models  # noqa: F401  (registers every table on Base)
from src.core.database import init_db
from src.models.base import Base
from src.repositories.annotation_repository import AnnotationRepository

# The tables as first deployed. A released database keeps this shape until init_db
# changes it, so do not edit these to make a test pass.
DEPLOYED_TABLES = (
    "CREATE TABLE services (id INTEGER NOT NULL, name VARCHAR NOT NULL, description VARCHAR, "
    "port INTEGER, health_endpoint VARCHAR, base_url VARCHAR, status VARCHAR(10) NOT NULL, "
    "systemd_state VARCHAR NOT NULL, last_scanned_at DATETIME, created_at DATETIME NOT NULL, "
    "updated_at DATETIME NOT NULL, PRIMARY KEY (id))",
    "CREATE TABLE annotations (id INTEGER NOT NULL, identity_key VARCHAR NOT NULL, "
    "display_name VARCHAR, description VARCHAR, hidden BOOLEAN, link_override VARCHAR, "
    "health_path VARCHAR, primary_port INTEGER, "
    "description_from_page BOOLEAN DEFAULT (0) NOT NULL, "
    "health_path_from_page BOOLEAN DEFAULT (0) NOT NULL, created_at DATETIME NOT NULL, "
    "updated_at DATETIME NOT NULL, PRIMARY KEY (id))",
    "CREATE TABLE registration_attempts (id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
    "identity_key VARCHAR NOT NULL, name VARCHAR NOT NULL, description VARCHAR, "
    "base_url VARCHAR, health_endpoint VARCHAR, held_fields JSON NOT NULL, "
    "received_at DATETIME NOT NULL)",
)


def test_init_db_adds_page_protection_columns_to_an_existing_annotations_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/old.db")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE annotations (id INTEGER PRIMARY KEY, "
                "identity_key VARCHAR NOT NULL UNIQUE, display_name VARCHAR, "
                "description VARCHAR, hidden BOOLEAN, link_override VARCHAR, "
                "health_path VARCHAR, primary_port INTEGER, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO annotations (identity_key, description, health_path, "
                "created_at, updated_at) VALUES ('system:old.service', 'Old', '/health', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    init_db(engine, user_unit_exists=lambda name: False)

    columns = {c["name"] for c in inspect(engine).get_columns("annotations")}
    assert {"description_from_page", "health_path_from_page"} <= columns
    session = sessionmaker(bind=engine)()
    try:
        note = AnnotationRepository(session).get("system:old.service")
        assert (note.description, note.health_path) == ("Old", "/health")
        assert (note.description_from_page, note.health_path_from_page) == (False, False)
    finally:
        session.close()
    engine.dispose()


def test_init_db_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/new.db")

    init_db(engine, user_unit_exists=lambda name: False)
    init_db(engine, user_unit_exists=lambda name: False)

    columns = [c["name"] for c in inspect(engine).get_columns("annotations")]
    assert columns.count("description_from_page") == 1
    engine.dispose()


def test_init_db_gives_a_deployed_database_every_model_column(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/deployed.db")
    with engine.begin() as conn:
        for statement in DEPLOYED_TABLES:
            conn.execute(text(statement))

    init_db(engine, user_unit_exists=lambda name: False)

    inspector = inspect(engine)
    missing = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if column.name not in {c["name"] for c in inspector.get_columns(table.name)}
    ]
    engine.dispose()
    assert not missing, (
        f"{missing} never reach an existing database, so every query on those tables would fail "
        "there. create_all does not alter existing tables: add the columns in init_db "
        "(src/core/database.py)."
    )

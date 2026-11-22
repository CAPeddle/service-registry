"""init_db brings a database created by an earlier build up to the current schema."""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.core.database import init_db
from src.repositories.annotation_repository import AnnotationRepository


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

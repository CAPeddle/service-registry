"""Tests for the one-time import of configured services into annotations."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.core.database import init_db
from src.repositories.annotation_repository import AnnotationRepository


def make_engine(rows=()):
    """Engine with an old-style services table holding the given rows."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE services (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL UNIQUE, "
            "description VARCHAR, port INTEGER, health_endpoint VARCHAR, base_url VARCHAR, "
            "status VARCHAR NOT NULL, systemd_state VARCHAR NOT NULL, last_scanned_at DATETIME, "
            "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        ))
        for r in rows:
            conn.execute(text(
                "INSERT INTO services (name, description, port, health_endpoint, base_url, status, systemd_state) "
                "VALUES (:name, :description, :port, :health_endpoint, :base_url, :status, :systemd_state)"
            ), {"port": None, "health_endpoint": None, "base_url": None, "description": None, **r})
    return engine


FINANCE = dict(name="finance-tracker.service", description="Finance tracker", port=8001,
               base_url="http://192.168.2.24:8001", status="CONFIGURED", systemd_state="active")
AH = dict(name="ah-connector.service", description="AH connector", health_endpoint="/health",
          status="CONFIGURED", systemd_state="unknown")


def annotations(engine):
    session = sessionmaker(bind=engine)()
    try:
        return {a.identity_key: a for a in AnnotationRepository(session).list()}
    finally:
        session.close()


def test_finance_tracker_imports_as_system_unit_without_link_override():
    engine = make_engine([FINANCE])
    init_db(engine, user_unit_exists=lambda name: False)

    imported = annotations(engine)
    assert list(imported) == ["system:finance-tracker.service"]
    a = imported["system:finance-tracker.service"]
    assert a.description == "Finance tracker"
    assert a.link_override is None


def test_api_registered_row_resolves_to_user_unit_when_it_exists():
    engine = make_engine([AH])
    init_db(engine, user_unit_exists=lambda name: name == "ah-connector.service")

    imported = annotations(engine)
    assert list(imported) == ["user:1000:ah-connector.service"]
    a = imported["user:1000:ah-connector.service"]
    assert a.description == "AH connector"
    assert a.health_path == "/health"


def test_api_registered_row_becomes_manual_when_no_user_unit():
    engine = make_engine([AH])
    init_db(engine, user_unit_exists=lambda name: False)

    assert list(annotations(engine)) == ["manual:ah-connector.service"]


def test_second_startup_keeps_user_edits_and_adds_no_duplicates():
    engine = make_engine([FINANCE, AH])
    exists = lambda name: True
    init_db(engine, user_unit_exists=exists)

    session = sessionmaker(bind=engine)()
    AnnotationRepository(session).upsert("system:finance-tracker.service", description="Edited", hidden=True)
    session.close()

    init_db(engine, user_unit_exists=exists)

    imported = annotations(engine)
    assert len(imported) == 2
    assert imported["system:finance-tracker.service"].description == "Edited"
    assert imported["system:finance-tracker.service"].hidden is True


def test_fresh_database_without_services_table_has_no_annotations():
    engine = create_engine("sqlite://")
    init_db(engine, user_unit_exists=lambda name: True)

    assert annotations(engine) == {}


def test_raw_and_discovered_rows_are_not_imported():
    engine = make_engine([
        dict(name="cron.service", status="RAW", systemd_state="active"),
        dict(name="web.service", status="DISCOVERED", systemd_state="active", port=80),
    ])
    init_db(engine, user_unit_exists=lambda name: True)

    assert annotations(engine) == {}

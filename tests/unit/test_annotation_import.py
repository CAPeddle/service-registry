"""Tests for the one-time import of configured services into annotations."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.core.database import init_db
from src.repositories.annotation_repository import AnnotationRepository


def make_engine(rows=(), url="sqlite://"):
    """Engine with an old-style services table holding the given rows."""
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE services (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL UNIQUE, "
                "description VARCHAR, port INTEGER, health_endpoint VARCHAR, base_url VARCHAR, "
                "status VARCHAR NOT NULL, systemd_state VARCHAR NOT NULL, "
                "last_scanned_at DATETIME, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        )
        for r in rows:
            conn.execute(
                text(
                    "INSERT INTO services (name, description, port, health_endpoint, base_url, "
                    "status, systemd_state) VALUES (:name, :description, :port, "
                    ":health_endpoint, :base_url, :status, :systemd_state)"
                ),
                {"port": None, "health_endpoint": None, "base_url": None, "description": None, **r},
            )
    return engine


FINANCE = dict(
    name="finance-tracker.service",
    description="Finance tracker",
    port=8001,
    base_url="http://192.168.2.24:8001",
    status="CONFIGURED",
    systemd_state="active",
)
AH = dict(
    name="ah-connector.service",
    description="AH connector",
    health_endpoint="/health",
    status="CONFIGURED",
    systemd_state="unknown",
)


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


def test_manual_row_keeps_its_link():
    engine = make_engine([{**AH, "base_url": "http://nas.example:5000/"}])
    init_db(engine, user_unit_exists=lambda name: False)

    note = annotations(engine)["manual:ah-connector.service"]
    assert note.link_override == "http://nas.example:5000/"


def test_unit_row_drops_its_old_link():
    engine = make_engine([FINANCE, {**AH, "base_url": "http://192.168.2.24:8772"}])
    init_db(engine, user_unit_exists=lambda name: True)

    assert {k: a.link_override for k, a in annotations(engine).items()} == {
        "system:finance-tracker.service": None,
        "user:1000:ah-connector.service": None,
    }


@pytest.mark.parametrize("url", [None, "", "javascript:alert(1)", "nas.example:5000"])
def test_manual_row_drops_a_value_that_is_not_an_http_link(url):
    engine = make_engine([{**AH, "base_url": url}])
    init_db(engine, user_unit_exists=lambda name: False)

    assert annotations(engine)["manual:ah-connector.service"].link_override is None


def test_deleted_annotations_do_not_return_after_a_restart(tmp_path):
    url = f"sqlite:///{tmp_path}/old.db"
    engine = make_engine([FINANCE, AH], url)
    init_db(engine, user_unit_exists=lambda name: False)
    session = sessionmaker(bind=engine)()
    for key in list(annotations(engine)):
        assert AnnotationRepository(session).delete(key)
    session.close()
    engine.dispose()

    restarted = create_engine(url)
    init_db(restarted, user_unit_exists=lambda name: False)

    assert annotations(restarted) == {}
    restarted.dispose()


def test_annotations_from_a_build_without_the_marker_count_as_imported():
    engine = make_engine([FINANCE, AH])
    init_db(engine, user_unit_exists=lambda name: True)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA user_version = 0"))  # as an earlier build left it
        conn.execute(text("DELETE FROM annotations WHERE identity_key LIKE 'user:%'"))

    init_db(engine, user_unit_exists=lambda name: True)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM annotations"))
    init_db(engine, user_unit_exists=lambda name: True)

    assert annotations(engine) == {}


def test_failed_import_stores_nothing_and_is_retried(tmp_path):
    engine = make_engine([FINANCE, AH], f"sqlite:///{tmp_path}/old.db")

    def broken(name):
        raise OSError("unit directory unreadable")

    with pytest.raises(OSError):
        init_db(engine, user_unit_exists=broken)
    assert annotations(engine) == {}

    init_db(engine, user_unit_exists=lambda name: True)
    assert len(annotations(engine)) == 2
    engine.dispose()


def test_second_startup_keeps_user_edits_and_adds_no_duplicates():
    engine = make_engine([FINANCE, AH])

    def exists(name):
        return True

    init_db(engine, user_unit_exists=exists)

    session = sessionmaker(bind=engine)()
    AnnotationRepository(session).upsert(
        "system:finance-tracker.service", description="Edited", hidden=True
    )
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
    engine = make_engine(
        [
            dict(name="cron.service", status="RAW", systemd_state="active"),
            dict(name="web.service", status="DISCOVERED", systemd_state="active", port=80),
        ]
    )
    init_db(engine, user_unit_exists=lambda name: True)

    assert annotations(engine) == {}

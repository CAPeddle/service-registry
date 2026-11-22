"""The services API: registrations and page edits stored as annotations by identity key."""
import pytest
from fastapi.testclient import TestClient

from src.api.dependencies.services import get_health_check_service, get_inventory_service
from src.api.main import app
from src.models.base import Base, SessionLocal, engine
from src.repositories.annotation_repository import AnnotationRepository
from src.repositories.registration_attempt_repository import RegistrationAttemptRepository
from src.services.discovery.inventory import AccessPath, Inventory, InventoryRow


def make_row(key, name, origin):
    return InventoryRow(
        identity_key=key,
        display_name=name,
        description=None,
        origin=origin,
        state="running",
        group="internal",
        hidden=False,
        suppressed=False,
        access_paths=(AccessPath(8772, "internal", None, True),),
        primary_port=8772,
        health_path=None,
        link_override=None,
    )


ROWS = [
    make_row("user:1000:ah-connector.service", "ah-connector", "user"),
    make_row("system:finance-tracker.service", "Finance tracker", "system"),
    make_row("docker:awcp/web", "awcp-web-1", "docker"),
    make_row("docker:clockme", "clockme", "docker"),
]


class FakeInventory:
    def __init__(self, rows):
        self.rows = rows

    def get(self, *, refresh=False):
        return Inventory(rows=list(self.rows), errors=[])


class NoProbes:
    async def probe_batch(self, requests):
        raise AssertionError("the API must not probe ports")


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def overrides():
    """Never run real discovery commands from these tests."""
    app.dependency_overrides[get_inventory_service] = lambda: FakeInventory(ROWS)
    app.dependency_overrides[get_health_check_service] = lambda: NoProbes()
    yield app.dependency_overrides
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def stored(key):
    session = SessionLocal()
    try:
        return AnnotationRepository(session).get(key)
    finally:
        session.close()


def annotate(key, **fields):
    session = SessionLocal()
    try:
        AnnotationRepository(session).upsert(key, **fields)
    finally:
        session.close()


AH_REGISTRATION = {
    "name": "ah-connector.service",
    "description": "Albert Heijn connector",
    "base_url": "http://127.0.0.1:8772",
    "port": 8772,
    "health_endpoint": "/health",
}

# Registration (the existing request shape)


def test_registration_matching_a_unit_annotates_it_without_a_link(client):
    response = client.post("/api/services", json=AH_REGISTRATION)

    assert response.status_code == 201
    assert response.json() == {
        "identity_key": "user:1000:ah-connector.service",
        "display_name": None,
        "description": "Albert Heijn connector",
        "hidden": None,
        "link_override": None,
        "health_path": "/health",
        "primary_port": None,
    }
    assert stored("manual:ah-connector.service") is None


def test_repeat_registration_updates_the_same_annotation(client):
    annotate("user:1000:ah-connector.service", display_name="AH", hidden=False)

    client.post("/api/services", json={**AH_REGISTRATION, "description": "New text"})

    note = stored("user:1000:ah-connector.service")
    assert (note.description, note.display_name, note.hidden) == ("New text", "AH", False)


@pytest.mark.parametrize(
    "name, key",
    [
        ("finance-tracker.service", "system:finance-tracker.service"),
        ("web", "docker:awcp/web"),
        ("clockme", "docker:clockme"),
    ],
)
def test_registration_matches_unit_compose_service_or_container_name(client, name, key):
    response = client.post(
        "/api/services",
        json={"name": name, "description": "d", "base_url": "http://192.168.2.24:8001"},
    )

    assert response.status_code == 201
    assert response.json()["identity_key"] == key
    assert response.json()["link_override"] is None


def test_registration_falls_back_to_an_existing_annotation(client, overrides):
    overrides[get_inventory_service] = lambda: FakeInventory([])
    annotate("user:1000:old.service", health_path="/old")

    response = client.post(
        "/api/services",
        json={
            "name": "old.service",
            "description": "d",
            "base_url": "http://127.0.0.1:9000",
            "health_endpoint": "/health",
        },
    )

    assert response.json()["identity_key"] == "user:1000:old.service"
    assert response.json()["health_path"] == "/health"
    assert response.json()["link_override"] is None


def test_registration_matching_nothing_becomes_manual_with_its_url(client):
    response = client.post(
        "/api/services",
        json={
            "name": "printer",
            "description": "Office printer",
            "base_url": "http://printer.lan/",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["identity_key"] == "manual:printer"
    assert body["link_override"] == "http://printer.lan/"
    assert body["description"] == "Office printer"


def test_repeat_manual_registration_updates_its_link(client):
    client.post(
        "/api/services",
        json={"name": "printer", "description": "d", "base_url": "http://printer.lan/"},
    )
    client.post(
        "/api/services",
        json={"name": "printer", "description": "d", "base_url": "http://printer2.lan/"},
    )

    assert stored("manual:printer").link_override == "http://printer2.lan/"


@pytest.mark.parametrize(
    "change",
    [
        {"base_url": "printer.lan"},
        {"base_url": "ftp://printer.lan/"},
        {"health_endpoint": "health"},
    ],
)
def test_registration_validation(client, change):
    data = {"name": "printer", "description": "d", "base_url": "http://printer.lan/", **change}

    assert client.post("/api/services", json=data).status_code == 422


# Page edits by identity key


def test_edit_creates_the_annotation_when_none_exists(client):
    response = client.put(
        "/api/services/annotation",
        json={"identity_key": "docker:app/app", "display_name": "Clock me", "hidden": True},
    )

    assert response.status_code == 200
    assert response.json()["identity_key"] == "docker:app/app"
    note = stored("docker:app/app")
    assert (note.display_name, note.hidden) == ("Clock me", True)


def test_hide_toggle_leaves_other_fields_alone(client):
    annotate("docker:app/app", display_name="Clock me", health_path="/health", primary_port=3000)

    client.put("/api/services/annotation", json={"identity_key": "docker:app/app", "hidden": False})

    note = stored("docker:app/app")
    assert (note.display_name, note.health_path, note.primary_port, note.hidden) == (
        "Clock me",
        "/health",
        3000,
        False,
    )


def test_edit_stores_all_fields_and_blank_clears(client):
    client.put(
        "/api/services/annotation",
        json={
            "identity_key": "user:1000:ntfy.service",
            "display_name": "ntfy",
            "description": "Push notifications",
            "link_override": "https://ntfy.example/",
            "health_path": "/v1/health",
            "primary_port": 8090,
        },
    )
    note = stored("user:1000:ntfy.service")
    assert (
        note.display_name,
        note.description,
        note.link_override,
        note.health_path,
        note.primary_port,
    ) == ("ntfy", "Push notifications", "https://ntfy.example/", "/v1/health", 8090)

    client.put(
        "/api/services/annotation",
        json={
            "identity_key": "user:1000:ntfy.service",
            "display_name": "",
            "description": " ",
            "link_override": "",
            "health_path": "",
            "primary_port": None,
            "hidden": None,
        },
    )
    note = stored("user:1000:ntfy.service")
    assert (
        note.display_name,
        note.description,
        note.link_override,
        note.health_path,
        note.primary_port,
        note.hidden,
    ) == (None, None, None, None, None, None)


@pytest.mark.parametrize(
    "change",
    [
        {"link_override": "javascript:alert(1)"},
        {"link_override": "printer.lan"},
        {"health_path": "health"},
        {"primary_port": 0},
        {"primary_port": 65536},
        {"identity_key": ""},
    ],
)
def test_edit_validation(client, change):
    data = {"identity_key": "docker:app/app", **change}

    assert client.put("/api/services/annotation", json=data).status_code == 422


def test_list_and_delete_annotations(client):
    annotate("docker:app/app", display_name="Clock me")
    annotate("manual:printer", link_override="http://printer.lan/")

    listed = client.get("/api/services").json()
    assert [a["identity_key"] for a in listed] == ["docker:app/app", "manual:printer"]

    response = client.delete("/api/services/annotation", params={"identity_key": "docker:app/app"})
    assert response.status_code == 204
    assert stored("docker:app/app") is None

    response = client.delete("/api/services/annotation", params={"identity_key": "docker:app/app"})
    assert response.status_code == 404


# Removed surface


def test_cross_origin_preflight_is_not_allowed(client):
    response = client.options(
        "/api/services",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_scan_workflow_is_gone(client):
    assert client.get("/scan").status_code == 404
    assert client.post("/api/scan").status_code == 404


@pytest.mark.parametrize(
    "key",
    [
        "user:²:x.service",
        "user:1000:",
        "user:abc:x.service",
        "system:",
        "docker:",
        "manual:",
        "process:",
        "docker-proxy:abc",
        "docker-proxy:",
        "nonsense:x",
        "no-colon",
    ],
)
def test_edit_rejects_malformed_identity_keys(client, key):
    response = client.put("/api/services/annotation", json={"identity_key": key, "hidden": True})

    assert response.status_code == 422
    assert stored(key) is None


@pytest.mark.parametrize(
    "key",
    [
        "system:x.service",
        "user:1000:x.service",
        "docker:proj/svc",
        "docker:container",
        "manual:printer",
        "docker-proxy:8080",
        "process:unknown process",
    ],
)
def test_edit_accepts_every_identity_key_the_inventory_produces(client, key):
    response = client.put("/api/services/annotation", json={"identity_key": key, "hidden": True})

    assert response.status_code == 200
    assert stored(key).hidden is True


# Page edits win over registrations; conflicting registrations are held


AH_KEY = "user:1000:ah-connector.service"


def page_edit(client, **fields):
    response = client.put("/api/services/annotation", json={"identity_key": AH_KEY, **fields})
    assert response.status_code == 200


def held():
    session = SessionLocal()
    try:
        return RegistrationAttemptRepository(session).list()
    finally:
        session.close()


def test_registration_on_a_fresh_service_applies_and_holds_nothing(client):
    response = client.post("/api/services", json=AH_REGISTRATION)

    assert response.status_code == 201
    note = stored(AH_KEY)
    assert (note.description, note.health_path) == ("Albert Heijn connector", "/health")
    assert held() == []


def test_page_edited_description_survives_a_registration_and_the_attempt_is_held(client):
    page_edit(client, description="My own words")

    response = client.post("/api/services", json=AH_REGISTRATION)

    assert response.status_code == 201
    assert response.json()["description"] == "My own words"
    assert response.json()["health_path"] == "/health"
    note = stored(AH_KEY)
    assert (note.description, note.health_path) == ("My own words", "/health")
    [attempt] = held()
    assert attempt.identity_key == AH_KEY
    assert attempt.name == "ah-connector.service"
    assert attempt.description == "Albert Heijn connector"
    assert attempt.base_url == "http://127.0.0.1:8772"
    assert attempt.health_endpoint == "/health"
    assert attempt.held_fields == ["description"]
    assert attempt.received_at is not None


def test_registration_with_the_same_value_as_the_page_edit_holds_nothing(client):
    page_edit(client, description="Albert Heijn connector")

    client.post("/api/services", json=AH_REGISTRATION)

    assert held() == []


def test_page_edited_health_path_is_protected_too(client):
    page_edit(client, health_path="/ready")

    client.post("/api/services", json=AH_REGISTRATION)

    note = stored(AH_KEY)
    assert (note.description, note.health_path) == ("Albert Heijn connector", "/ready")
    [attempt] = held()
    assert attempt.held_fields == ["health_path"]


def test_registration_without_a_health_endpoint_keeps_a_protected_one_and_holds_nothing(client):
    page_edit(client, health_path="/ready")

    client.post("/api/services", json={**AH_REGISTRATION, "health_endpoint": None})

    assert stored(AH_KEY).health_path == "/ready"
    assert held() == []


def test_both_protected_fields_are_held_together(client):
    page_edit(client, description="Mine", health_path="/ready")

    client.post("/api/services", json=AH_REGISTRATION)

    [attempt] = held()
    assert attempt.held_fields == ["description", "health_path"]


def test_a_later_held_registration_replaces_the_pending_one_for_that_service(client):
    page_edit(client, description="Mine")

    client.post("/api/services", json={**AH_REGISTRATION, "description": "First"})
    client.post("/api/services", json={**AH_REGISTRATION, "description": "Second"})

    [attempt] = held()
    assert attempt.description == "Second"


def test_clearing_a_field_on_the_page_removes_its_protection(client):
    page_edit(client, description="Mine", health_path="/ready")
    page_edit(client, description="", health_path="")

    client.post("/api/services", json=AH_REGISTRATION)

    note = stored(AH_KEY)
    assert (note.description, note.health_path) == ("Albert Heijn connector", "/health")
    assert held() == []


def test_edits_to_other_fields_leave_protection_alone(client):
    page_edit(client, description="Mine")
    page_edit(client, hidden=True, display_name="AH")

    client.post("/api/services", json=AH_REGISTRATION)

    assert stored(AH_KEY).description == "Mine"
    assert len(held()) == 1


def test_using_held_values_copies_them_clears_protection_and_removes_the_attempt(client):
    page_edit(client, description="Mine", health_path="/ready")
    client.post("/api/services", json=AH_REGISTRATION)
    [attempt] = held()

    response = client.post(f"/api/services/registrations/{attempt.id}/apply")

    assert response.status_code == 200
    assert response.json()["description"] == "Albert Heijn connector"
    note = stored(AH_KEY)
    assert (note.description, note.health_path) == ("Albert Heijn connector", "/health")
    assert (note.description_from_page, note.health_path_from_page) == (False, False)
    assert held() == []

    client.post("/api/services", json={**AH_REGISTRATION, "description": "Newer"})
    assert stored(AH_KEY).description == "Newer"
    assert held() == []


def test_using_held_values_leaves_fields_that_were_not_held_alone(client):
    page_edit(client, description="Mine")
    client.post("/api/services", json=AH_REGISTRATION)
    page_edit(client, health_path="/ready")
    [attempt] = held()

    client.post(f"/api/services/registrations/{attempt.id}/apply")

    note = stored(AH_KEY)
    assert (note.description, note.health_path) == ("Albert Heijn connector", "/ready")
    assert note.health_path_from_page is True


def test_dismissing_a_held_registration_removes_it_and_changes_nothing(client):
    page_edit(client, description="Mine")
    client.post("/api/services", json=AH_REGISTRATION)
    [attempt] = held()

    response = client.delete(f"/api/services/registrations/{attempt.id}")

    assert response.status_code == 204
    assert held() == []
    assert stored(AH_KEY).description == "Mine"
    assert stored(AH_KEY).description_from_page is True


def test_unknown_held_registration_is_404(client):
    for response in (
        client.post("/api/services/registrations/999/apply"),
        client.delete("/api/services/registrations/999"),
    ):
        assert response.status_code == 404
        assert response.json() == {"detail": "Held registration not found"}


FINANCE_KEY = "system:finance-tracker.service"
FINANCE_REGISTRATION = {
    "name": "finance-tracker.service",
    "description": "Finance tracker",
    "base_url": "http://127.0.0.1:8001",
}


def test_held_registration_ids_are_not_reused(client):
    page_edit(client, description="Mine")
    client.post("/api/services", json=AH_REGISTRATION)
    [first] = held()
    client.delete(f"/api/services/registrations/{first.id}")
    client.put("/api/services/annotation", json={"identity_key": FINANCE_KEY, "description": "Own"})

    assert client.post("/api/services", json=FINANCE_REGISTRATION).status_code == 201

    [second] = held()
    assert second.identity_key == FINANCE_KEY
    assert second.id != first.id
    assert client.post(f"/api/services/registrations/{first.id}/apply").status_code == 404


def test_a_registration_that_holds_nothing_removes_the_pending_one(client):
    page_edit(client, description="Mine")
    client.post("/api/services", json=AH_REGISTRATION)
    assert len(held()) == 1

    client.post("/api/services", json={**AH_REGISTRATION, "description": "Mine"})

    assert held() == []


def test_clearing_a_held_field_on_the_page_releases_it_from_the_pending_registration(client):
    page_edit(client, description="Mine", health_path="/ready")
    client.post("/api/services", json=AH_REGISTRATION)

    page_edit(client, health_path="")

    [attempt] = held()
    assert attempt.held_fields == ["description"]

    page_edit(client, description="")

    assert held() == []


def test_using_held_values_after_protection_was_cleared_does_not_roll_back(client):
    page_edit(client, description="Mine", health_path="/ready")
    client.post("/api/services", json=AH_REGISTRATION)
    [attempt] = held()
    page_edit(client, health_path="")

    response = client.post(f"/api/services/registrations/{attempt.id}/apply")

    assert response.status_code == 200
    note = stored(AH_KEY)
    assert (note.description, note.health_path) == ("Albert Heijn connector", None)
    assert held() == []


def test_using_held_values_skips_fields_no_longer_protected(client):
    page_edit(client, description="Mine", health_path="/ready")
    client.post("/api/services", json=AH_REGISTRATION)
    [attempt] = held()
    annotate(AH_KEY, health_path="/live", health_path_from_page=False)

    client.post(f"/api/services/registrations/{attempt.id}/apply")

    note = stored(AH_KEY)
    assert (note.description, note.health_path) == ("Albert Heijn connector", "/live")
    assert held() == []


def test_deleting_an_annotation_removes_its_pending_registration(client):
    page_edit(client, description="Mine")
    client.post("/api/services", json=AH_REGISTRATION)

    client.delete("/api/services/annotation", params={"identity_key": AH_KEY})

    assert held() == []


def test_using_held_values_for_a_deleted_annotation_is_404(client):
    page_edit(client, description="Mine")
    client.post("/api/services", json=AH_REGISTRATION)
    [attempt] = held()
    session = SessionLocal()
    try:
        AnnotationRepository(session).delete(AH_KEY)
    finally:
        session.close()

    response = client.post(f"/api/services/registrations/{attempt.id}/apply")

    assert response.status_code == 404
    assert response.json() == {"detail": "Annotation not found"}
    assert stored(AH_KEY) is None
    assert held() == []

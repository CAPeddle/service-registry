"""Write requests must come from a trusted Host and the same origin, so other sites cannot write."""
import json

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from src.api.dependencies.services import get_health_check_service, get_inventory_service
from src.api.main import app
from src.config import settings
from src.models.base import Base, engine, get_db
from src.repositories.annotation_repository import AnnotationRepository
from src.services.discovery import SourceError
from src.services.discovery.cache import TtlCache
from src.services.discovery.inventory import InventoryService, SourceSnapshot
from src.services.discovery.tailscale_serve import ServeMapping

FQDN = "z2.example-tailnet.ts.net"
EDIT = {"identity_key": "docker:app/app", "hidden": True}


class NoProbes:
    async def probe_batch(self, requests):
        return {}


def inventory_service(db, serve):
    """A real inventory service whose only source result is the given serve mappings."""
    failed = SourceError("test", "not used")
    snapshot = SourceSnapshot(
        sockets=[],
        cgroups={},
        docker={},
        serve=serve,
        firewall=failed,
        show_unit=lambda unit, uid=None: failed,
    )
    return InventoryService(TtlCache(lambda: snapshot), AnnotationRepository(db))


def use_serve(overrides, serve):
    def provider(db=Depends(get_db)):
        return inventory_service(db, serve)

    overrides[get_inventory_service] = provider


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def overrides():
    use_serve(app.dependency_overrides, [ServeMapping(443, f"https://{FQDN}/", "127.0.0.1", 8790)])
    app.dependency_overrides[get_health_check_service] = lambda: NoProbes()
    yield app.dependency_overrides
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def edit(client, host, origin=None):
    headers = {"Host": host}
    if origin is not None:
        headers["Origin"] = origin
    return client.put("/api/services/annotation", json=EDIT, headers=headers).status_code


@pytest.mark.parametrize(
    "host",
    [
        "192.168.2.48",
        "192.168.2.48:80",
        "z2",
        "Z2:8000",
        "localhost",
        "testserver",
        "z2.local",
        "Z2.LOCAL",
        "[fd4e::1]",
        "[fd4e::1]:80",
        FQDN,
        f"{FQDN.upper()}:80",
    ],
)
def test_writes_from_a_trusted_host_are_allowed(client, host):
    assert edit(client, host) == 200


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:80",
        "z2.evil.example",
        "local.evil.example",
        f"{FQDN}.evil.example",
        "evil.ts.net",
        "[not-an-address]",
        "z2\nfoo",
        "",
    ],
)
def test_writes_from_another_host_are_forbidden(client, host):
    assert edit(client, host) == 403


@pytest.mark.parametrize(
    "origin", ["http://evil.example", "http://evil.example:80", "null", "junk"]
)
def test_untrusted_origin_is_forbidden_even_from_a_trusted_host(client, origin):
    assert edit(client, "192.168.2.48", origin=origin) == 403


@pytest.mark.parametrize(
    "host, origin",
    [
        ("192.168.2.48", "http://192.168.2.48"),
        ("z2", "http://z2"),
        ("z2:80", "http://z2:8080"),
        ("Z2", "http://z2"),
        ("[fd4e::1]:80", "http://[fd4e::1]"),
        (FQDN, f"https://{FQDN}"),
    ],
)
def test_origin_naming_the_request_host_is_allowed(client, host, origin):
    assert edit(client, host, origin=origin) == 200


@pytest.mark.parametrize(
    "host, origin",
    [
        ("192.168.2.48", "http://203.0.113.5"),
        ("192.168.2.48", "http://z2"),
        ("z2", "http://192.168.2.48"),
        ("192.168.2.48", f"https://{FQDN}"),
    ],
)
def test_origin_naming_another_trusted_host_is_forbidden(client, host, origin):
    assert edit(client, host, origin=origin) == 403


@pytest.mark.parametrize("site", ["cross-site", "same-site", "junk"])
def test_cross_site_fetch_is_forbidden_even_with_matching_host_and_origin(client, site):
    headers = {"Host": "z2", "Origin": "http://z2", "Sec-Fetch-Site": site}
    response = client.put("/api/services/annotation", json=EDIT, headers=headers)

    assert response.status_code == 403


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_same_origin_or_user_initiated_fetch_is_allowed(client, site):
    headers = {"Host": "z2", "Origin": "http://z2", "Sec-Fetch-Site": site}
    response = client.put("/api/services/annotation", json=EDIT, headers=headers)

    assert response.status_code == 200


REGISTRATION = {"name": "printer", "description": "d", "base_url": "http://printer.lan/"}


@pytest.mark.parametrize("content_type", [None, "text/plain", "application/x-www-form-urlencoded"])
def test_a_write_body_that_is_not_declared_json_is_rejected(client, content_type):
    headers = {} if content_type is None else {"Content-Type": content_type}
    body = json.dumps(REGISTRATION)

    response = client.post("/api/services", content=body, headers=headers)

    assert response.status_code == 415
    assert client.get("/api/services").json() == []


def test_a_chunked_write_body_must_be_declared_json(client):
    body = json.dumps(EDIT).encode()

    response = client.put("/api/services/annotation", content=iter([body]))

    assert response.status_code == 415


@pytest.mark.parametrize("content_type", ["application/json", "Application/JSON; charset=utf-8"])
def test_a_write_body_declared_json_is_accepted(client, content_type):
    body = json.dumps(REGISTRATION)

    response = client.post("/api/services", content=body, headers={"Content-Type": content_type})

    assert response.status_code == 201


def test_bodyless_write_from_a_foreign_origin_is_forbidden(client):
    for headers in (
        {"Host": "192.168.2.48", "Origin": "http://203.0.113.5"},
        {"Host": "192.168.2.48", "Sec-Fetch-Site": "cross-site"},
    ):
        response = client.post("/api/services/registrations/1/apply", headers=headers)
        assert response.status_code == 403


def test_the_landing_page_requests_pass(client):
    """The page's own fetch calls: same origin, JSON bodies, bodyless apply and dismiss."""
    page = {"Host": "z2:8000", "Origin": "http://z2:8000", "Sec-Fetch-Site": "same-origin"}

    assert client.put("/api/services/annotation", json=EDIT, headers=page).status_code == 200
    assert client.post("/api/services/registrations/1/apply", headers=page).status_code == 404
    assert client.delete("/api/services/registrations/1", headers=page).status_code == 404


def test_every_write_route_is_checked(client):
    headers = {"Host": "evil.example"}
    registration = {"name": "printer", "description": "d", "base_url": "http://printer.lan/"}

    assert client.post("/api/services", json=registration, headers=headers).status_code == 403
    assert client.put("/api/services/annotation", json=EDIT, headers=headers).status_code == 403
    response = client.delete(
        "/api/services/annotation", params={"identity_key": "manual:printer"}, headers=headers
    )
    assert response.status_code == 403
    assert client.post("/api/services/registrations/1/apply", headers=headers).status_code == 403
    assert client.delete("/api/services/registrations/1", headers=headers).status_code == 403
    assert client.get("/api/services").json() == []


def test_reads_are_not_restricted(client):
    headers = {"Host": "evil.example", "Origin": "http://evil.example"}

    assert client.get("/", headers=headers).status_code == 200
    assert client.get("/api/services", headers=headers).status_code == 200
    assert client.get("/api/v1/health", headers=headers).status_code == 200


def test_configured_trusted_hosts_are_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "trusted_hosts", " registry.example.org , Other.Example ")

    assert edit(client, "registry.example.org") == 200
    assert edit(client, "other.example:80") == 200
    assert edit(client, "Registry.example.org:80", origin="http://registry.example.org") == 200
    assert edit(client, "evil.example") == 403


def test_tailnet_name_is_not_trusted_when_serve_discovery_fails(client, overrides):
    use_serve(overrides, SourceError("tailscale", "tailscale: command not found"))

    assert edit(client, FQDN) == 403
    assert edit(client, "z2") == 200


def test_trusted_hosts_do_not_trigger_discovery(client, overrides):
    class Exploding:
        def get(self, *, refresh=False):
            raise AssertionError("discovery must not run for a trusted host")

    overrides[get_inventory_service] = lambda: Exploding()

    assert edit(client, "192.168.2.48") == 200

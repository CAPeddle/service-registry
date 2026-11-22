"""The landing page: grouped live inventory with visitor-relative links."""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from starlette.requests import Request

from src.api.dependencies.services import get_health_check_service, get_inventory_service
from src.api.main import app
from src.api.routes.pages import get_safe_hostname
from src.models.base import Base, engine, get_db
from src.repositories.annotation_repository import AnnotationRepository
from src.services.discovery import SourceError
from src.services.discovery.cache import TtlCache
from src.services.discovery.cgroups import parse_cgroup
from src.services.discovery.docker_ports import parse_docker_ps
from src.services.discovery.firewall import parse_ufw_status
from src.services.discovery.inventory import (
    AccessPath,
    Inventory,
    InventoryRow,
    InventoryService,
    Sources,
    collect_snapshot,
)
from src.services.discovery.sockets import parse_ss
from src.services.discovery.tailscale_serve import parse_serve_status
from src.services.discovery.units import UnitStatus
from src.services.health_check import HealthCheckService, HealthStatus, ProbeResult

FQDN = "z2.example-tailnet.ts.net"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "z2"


def make_row(
    key,
    name,
    group,
    paths=(),
    *,
    origin="user",
    state="running",
    hidden=False,
    suppressed=False,
    description=None,
    health_path=None,
    link_override=None,
    primary_port=None,
):
    paths = tuple(paths)
    if primary_port is None and paths:
        primary_port = next((p.port for p in paths if p.is_primary), paths[0].port)
    return InventoryRow(
        identity_key=key,
        display_name=name,
        description=description,
        origin=origin,
        state=state,
        group=group,
        hidden=hidden,
        suppressed=suppressed,
        access_paths=paths,
        primary_port=primary_port,
        health_path=health_path,
        link_override=link_override,
    )


def lan(port, primary=True):
    return AccessPath(port, "lan", None, primary)


def blocked(port, primary=True):
    return AccessPath(port, "lan_blocked", None, primary)


def tailnet(port, url, primary=True):
    return AccessPath(port, "tailnet", url, primary)


def internal(port, primary=True):
    return AccessPath(port, "internal", None, primary)


GROCERIES = make_row("user:1000:groceries-web.service", "groceries-web", "lan", [lan(8080)])
AWCP = make_row(
    "docker:awcp/awcp", "awcp", "tailnet", [tailnet(8790, f"https://{FQDN}/")], origin="docker"
)
AH_CONNECTOR = make_row(
    "user:1000:ah-connector.service", "ah-connector", "internal", [internal(8772)]
)


class FakeInventory:
    def __init__(self, rows=(), errors=()):
        self.inventory = Inventory(rows=list(rows), errors=list(errors))
        self.refresh_calls = []

    def get(self, *, refresh=False):
        self.refresh_calls.append(refresh)
        return self.inventory


class FakeProber:
    """Answers probes from fixed tables instead of opening sockets."""

    def __init__(self, http_ports=(), health=None, failed=()):
        self.http_ports = set(http_ports)
        self.health = health or {}  # port -> True (healthy) / False (unhealthy)
        self.failed = set(failed)
        self.requests = []

    async def probe_batch(self, requests):
        self.requests.extend(requests)
        results = {}
        for req in requests:
            if req.port in self.failed:
                results[req] = ProbeResult(checking_failed=True)
                continue
            health = None
            if req.health_path:
                healthy = self.health.get(req.port, True)
                health = HealthStatus(is_healthy=healthy, status_code=200 if healthy else 500)
            results[req] = ProbeResult(is_http=req.port in self.http_ports, health=health)
        return results


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def overrides():
    """Never run real discovery commands or probe real ports from these tests."""
    app.dependency_overrides[get_inventory_service] = lambda: FakeInventory()
    app.dependency_overrides[get_health_check_service] = lambda: FakeProber()
    yield app.dependency_overrides
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def serve(overrides, inventory, prober=None):
    overrides[get_inventory_service] = lambda: inventory
    prober = prober or FakeProber()
    overrides[get_health_check_service] = lambda: prober
    return prober


def fixture_inventory_service(db):
    """A real inventory service over the captured Z2 outputs and the test database."""
    cgroup_lines = {}
    for line in (FIXTURES / "cgroups.txt").read_text().splitlines():
        if line.strip():
            pid, cgroup_line = line.split()[:2]
            cgroup_lines[int(pid)] = cgroup_line

    def read_cgroup(pid):
        if pid not in cgroup_lines:
            return SourceError("cgroups", f"no cgroup for pid {pid}")
        return parse_cgroup(cgroup_lines[pid])

    sources = Sources(
        list_sockets=lambda: parse_ss((FIXTURES / "ss-root.txt").read_text()),
        read_cgroup=read_cgroup,
        list_published_ports=lambda: parse_docker_ps((FIXTURES / "docker-ps.jsonl").read_text()),
        list_serve_mappings=lambda: parse_serve_status(
            (FIXTURES / "tailscale-serve.json").read_text()
        ),
        read_firewall=lambda: parse_ufw_status((FIXTURES / "ufw-status.txt").read_text()),
        show_unit=lambda unit, uid=None: UnitStatus(
            description="", active_state="active", load_state="loaded"
        ),
    )
    snapshot = collect_snapshot(sources)
    return InventoryService(TtlCache(lambda: snapshot), AnnotationRepository(db))


def use_fixture_inventory(overrides):
    # Like the real provider, the annotations come from the request's session.
    def provider(db=Depends(get_db)):
        return fixture_inventory_service(db)

    overrides[get_inventory_service] = provider
    overrides[get_health_check_service] = lambda: FakeProber()


def row_html(html, key):
    """The markup of the row for one identity key."""
    marker = f'data-identity-key="{key}"'
    start = html.find(marker)
    assert start != -1, f"no row for {key}"
    start = html.rfind("<article", 0, start)
    end = html.find("</article>", start)
    return html[start:end]


def group_html(html, group):
    match = re.search(rf'<section[^>]*id="group-{group}"[^>]*>(.*?)</section>', html, re.S)
    assert match, f"no {group} group"
    return match.group(1)


def group_order(html):
    return re.findall(r'<section[^>]*id="group-([a-z_]+)"', html)


def page(client, host="192.168.2.48", **params):
    response = client.get("/", params=params, headers={"Host": host})
    assert response.status_code == 200
    return response.text


# Links built from the visitor's host


def test_lan_link_uses_the_address_the_visitor_browsed_to(client, overrides):
    serve(overrides, FakeInventory([GROCERIES]), FakeProber(http_ports={8080}))

    assert 'href="http://192.168.2.48:8080"' in page(client, host="192.168.2.48")
    assert 'href="http://z2:8080"' in page(client, host="z2")


def test_host_header_port_is_dropped(client, overrides):
    serve(overrides, FakeInventory([GROCERIES]), FakeProber(http_ports={8080}))

    assert 'href="http://z2:8080"' in page(client, host="z2:80")


def test_bracketed_ipv6_host_is_used_in_links(client, overrides):
    serve(overrides, FakeInventory([GROCERIES]), FakeProber(http_ports={8080}))

    assert 'href="http://[fd4e::1]:8080"' in page(client, host="[fd4e::1]")
    assert 'href="http://[fd4e::1]:8080"' in page(client, host="[fd4e::1]:80")


def _request_with_host(host: bytes) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [(b"host", host)]})


@pytest.mark.parametrize(
    "host",
    [
        b"z2\r\nX-Injected: 1",
        b"z2\nfoo",
        b"z2\n",
        b"[fd4e::1]\n",
        b"[fd4e::1]\r\n",
        b"[not-an-address]",
        b"[1:2:3]",
        b"[fd4e::1]junk",
        b"evil.example/path",
        b"",
    ],
)
def test_unsafe_host_falls_back_to_localhost(host):
    assert get_safe_hostname(_request_with_host(host)) == "localhost"


@pytest.mark.parametrize(
    "host, expected",
    [
        (b"192.168.2.48", "192.168.2.48"),
        (b"z2.example-tailnet.ts.net:80", "z2.example-tailnet.ts.net"),
        (b"[fd4e::1]", "[fd4e::1]"),
        (b"[fd4e::1]:8080", "[fd4e::1]"),
    ],
)
def test_safe_host_is_kept(host, expected):
    assert get_safe_hostname(_request_with_host(host)) == expected


def test_tailnet_link_is_the_serve_url_under_any_host(client, overrides):
    serve(overrides, FakeInventory([AWCP]), FakeProber(http_ports={8790}))

    for host in ("192.168.2.48", "z2", "100.65.192.115"):
        row = row_html(page(client, host=host), "docker:awcp/awcp")
        assert f'href="https://{FQDN}/"' in row
        assert "tailnet only" in row


# Ports without links


def test_internal_path_is_text_without_a_link(client, overrides):
    serve(overrides, FakeInventory([AH_CONNECTOR]), FakeProber(http_ports={8772}))

    row = row_html(page(client), "user:1000:ah-connector.service")
    assert "127.0.0.1:8772" in row
    assert "<a " not in row
    assert "internal only" in row


def test_firewall_blocked_lan_path_is_text_and_tailnet_path_still_links(client, overrides):
    groceries = make_row(
        "user:1000:groceries-web.service",
        "groceries-web",
        "tailnet",
        [blocked(8080), tailnet(8080, f"http://{FQDN}:8080")],
    )
    serve(overrides, FakeInventory([groceries]), FakeProber(http_ports={8080}))

    html = page(client)
    row = row_html(html, "user:1000:groceries-web.service")
    assert "192.168.2.48:8080" in row
    assert 'href="http://192.168.2.48:8080"' not in row
    assert "blocked by firewall" in row
    assert f'href="http://{FQDN}:8080"' in row
    assert "user:1000:groceries-web.service" in group_html(html, "tailnet")


def test_non_http_lan_port_gets_no_link(client, overrides):
    finance = make_row(
        "system:finance-tracker.service", "finance-tracker", "lan", [lan(8001)], origin="system"
    )
    serve(overrides, FakeInventory([finance]), FakeProber(http_ports=set()))

    row = row_html(page(client), "system:finance-tracker.service")
    assert "192.168.2.48:8001" in row
    assert "<a " not in row


def test_link_override_links_even_when_the_port_is_not_http(client, overrides):
    finance = make_row(
        "system:finance-tracker.service",
        "finance-tracker",
        "lan",
        [lan(8001)],
        origin="system",
        link_override="http://finance.example/",
    )
    serve(overrides, FakeInventory([finance]), FakeProber(http_ports=set()))

    row = row_html(page(client), "system:finance-tracker.service")
    assert 'href="http://finance.example/"' in row
    assert 'href="http://192.168.2.48:8001"' not in row


def test_port_whose_probe_timed_out_gets_no_link(client, overrides):
    serve(overrides, FakeInventory([GROCERIES]), FakeProber(http_ports={8080}, failed={8080}))

    row = row_html(page(client), "user:1000:groceries-web.service")
    assert "<a " not in row


def test_primary_path_is_listed_first(client, overrides):
    row = make_row(
        "user:1000:multi.service",
        "multi",
        "lan",
        [lan(3000, primary=False), lan(4000, primary=True)],
    )
    serve(overrides, FakeInventory([row]), FakeProber(http_ports={3000, 4000}))

    html = row_html(page(client), "user:1000:multi.service")
    assert html.index(":4000") < html.index(":3000")


# Health


def test_health_labels(client, overrides):
    rows = [
        make_row(
            "user:1000:good.service", "good", "internal", [internal(9001)], health_path="/health"
        ),
        make_row(
            "user:1000:bad.service", "bad", "internal", [internal(9002)], health_path="/health"
        ),
        make_row(
            "user:1000:slow.service", "slow", "internal", [internal(9003)], health_path="/health"
        ),
        make_row("user:1000:plain.service", "plain", "internal", [internal(9004)]),
    ]
    prober = serve(
        overrides, FakeInventory(rows), FakeProber(health={9001: True, 9002: False}, failed={9003})
    )

    html = page(client)
    assert "Health: healthy" in row_html(html, "user:1000:good.service")
    assert "Health: unhealthy" in row_html(html, "user:1000:bad.service")
    assert "Health: checking failed" in row_html(html, "user:1000:slow.service")
    assert "Health: not checked" in row_html(html, "user:1000:plain.service")
    assert {(r.port, r.health_path) for r in prober.requests} >= {
        (9001, "/health"),
        (9002, "/health"),
        (9003, "/health"),
        (9004, None),
    }


# Groups, hidden rows, banner and refresh


def test_groups_render_in_order_and_unknown_only_when_needed(client, overrides):
    rows = [
        make_row("user:1000:a.service", "a", "lan", [lan(8080)]),
        make_row("user:1000:b.service", "b", "tailnet", [tailnet(8090, f"http://{FQDN}:8090")]),
        make_row("user:1000:c.service", "c", "internal", [internal(8772)]),
        make_row("system:d.service", "d", "not_running", [], origin="system", state="failed"),
    ]
    serve(overrides, FakeInventory(rows))
    html = page(client)
    assert group_order(html) == ["lan", "tailnet", "internal", "not_running"]
    assert "failed" in row_html(html, "system:d.service")

    rows.append(
        make_row(
            "docker-proxy:9000",
            "docker-proxy",
            "unknown",
            [AccessPath(9000, "unknown", None, True)],
            origin="docker",
        )
    )
    serve(overrides, FakeInventory(rows))
    html = page(client)
    assert group_order(html) == ["unknown", "lan", "tailnet", "internal", "not_running"]
    assert "reachability unknown" in row_html(html, "docker-proxy:9000")


def test_hidden_rows_are_absent_by_default_and_shown_on_request(client, overrides):
    sshd = make_row(
        "system:ssh.service",
        "OpenBSD Secure Shell server",
        "lan",
        [lan(22)],
        origin="system",
        hidden=True,
        suppressed=True,
    )
    tmux = make_row(
        "process:python3",
        "python3",
        "internal",
        [internal(40000)],
        origin="other",
        hidden=True,
        suppressed=True,
    )
    prober = serve(overrides, FakeInventory([GROCERIES, sshd, tmux]))

    html = page(client)
    assert "system:ssh.service" not in html
    assert "process:python3" not in html
    assert 'href="/?show_hidden=1"' in html
    assert {r.port for r in prober.requests} == {8080}

    html = page(client, show_hidden="1")
    hidden = group_html(html, "hidden")
    assert "system:ssh.service" in hidden
    assert "process:python3" in hidden
    assert hidden.index("Other processes") < hidden.index("process:python3")
    assert "user:1000:groceries-web.service" not in hidden


def test_source_error_renders_a_banner_and_the_page_still_loads(client, overrides):
    errors = [
        SourceError("docker", "docker: command not found"),
        SourceError("firewall", "ufw timed out"),
    ]
    serve(overrides, FakeInventory([GROCERIES], errors))

    html = page(client)
    banner = re.search(r'<div[^>]*class="source-errors"[^>]*>(.*?)</div>', html, re.S).group(1)
    assert "docker" in banner
    assert "firewall" in banner


def test_refresh_bypasses_the_cache(client, overrides):
    inventory = FakeInventory([GROCERIES])
    serve(overrides, inventory)

    html = page(client)
    assert 'href="/?refresh=1"' in html
    page(client, refresh="1")
    assert inventory.refresh_calls == [False, True]


# Inline management


class AttributeCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.attributes = []

    def handle_starttag(self, tag, attrs):
        self.attributes.extend(attrs)


def test_page_edit_takes_effect_on_the_next_render(client, overrides):
    use_fixture_inventory(overrides)

    response = client.put(
        "/api/services/annotation",
        json={"identity_key": "docker:app/app", "display_name": "Clock me", "hidden": True},
    )
    assert response.status_code == 200

    html = page(client)
    assert "Clock me" not in html
    assert "docker:app/app" not in html

    hidden = group_html(page(client, show_hidden="1"), "hidden")
    assert "Clock me" in hidden
    assert 'data-hidden="true"' in row_html(hidden, "docker:app/app")


def test_row_values_reach_the_controls_only_through_data_attributes(client, overrides):
    use_fixture_inventory(overrides)
    name = "x');alert(1);//"
    response = client.post(
        "/api/services",
        json={
            "name": name,
            "description": "<img src=x onerror=alert(2)>",
            "base_url": "http://example.invalid/",
        },
    )
    assert response.status_code == 201

    html = page(client)
    collector = AttributeCollector()
    collector.feed(html)
    assert [n for n, _ in collector.attributes if n.lower().startswith("on")] == []
    assert ("data-display-name", name) in collector.attributes
    assert "<img src=x" not in html
    for script in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
        assert "alert(" not in script
        assert "x&#39;" not in script


def test_page_loads_when_no_shown_row_has_a_port_to_probe(client, overrides):
    absent = make_row(
        "system:finance-tracker.service",
        "finance-tracker",
        "unknown",
        [],
        origin="system",
        state="unknown",
    )
    serve(overrides, FakeInventory([absent], [SourceError("sockets", "ss failed")]))
    overrides[get_health_check_service] = lambda: HealthCheckService()

    html = page(client)
    assert "sockets" in re.search(r'class="source-errors"[^>]*>(.*?)</div>', html, re.S).group(1)
    assert "system:finance-tracker.service" in html


# Registrations held for review


def held_html(html):
    match = re.search(r'<section[^>]*id="held-registrations"[^>]*>(.*?)</section>', html, re.S)
    assert match, "no held registrations section"
    return match.group(1)


def test_no_held_section_without_held_registrations(client, overrides):
    serve(overrides, FakeInventory([AH_CONNECTOR]))

    assert 'id="held-registrations"' not in page(client)


def test_held_registration_is_shown_for_review_with_posted_and_current_values(client, overrides):
    serve(overrides, FakeInventory([AH_CONNECTOR]))
    key = "user:1000:ah-connector.service"
    client.put(
        "/api/services/annotation",
        json={"identity_key": key, "description": "<b>mine</b>", "health_path": "/ready"},
    )
    response = client.post(
        "/api/services",
        json={
            "name": "ah-connector.service",
            "description": "x');alert(1);//",
            "base_url": "http://127.0.0.1:8772",
            "health_endpoint": "/health",
        },
    )
    assert response.status_code == 201

    html = page(client)
    section = held_html(html)
    assert html.index('id="held-registrations"') < html.index('id="group-')
    assert "Registrations held for review" in html
    assert "ah-connector" in section
    assert "description" in section and "health path" in section
    assert "&lt;b&gt;mine&lt;/b&gt;" in section
    assert "/ready" in section and "/health" in section
    assert "Use these values" in section and "Dismiss" in section

    collector = AttributeCollector()
    collector.feed(html)
    assert [n for n, _ in collector.attributes if n.lower().startswith("on")] == []
    ids = {v for n, v in collector.attributes if n == "data-attempt-id"}
    assert len(ids) == 1
    assert "<b>mine</b>" not in html
    for script in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
        assert "alert(" not in script
        assert "mine" not in script


def test_held_registration_buttons_work_through_the_api(client, overrides):
    serve(overrides, FakeInventory([AH_CONNECTOR]))
    key = "user:1000:ah-connector.service"
    client.put("/api/services/annotation", json={"identity_key": key, "description": "mine"})
    registration = {
        "name": "ah-connector.service",
        "description": "posted",
        "base_url": "http://127.0.0.1:8772",
    }
    client.post("/api/services", json=registration)

    collector = AttributeCollector()
    collector.feed(page(client))
    [attempt_id] = {v for n, v in collector.attributes if n == "data-attempt-id"}
    assert client.post(f"/api/services/registrations/{attempt_id}/apply").status_code == 200
    assert 'id="held-registrations"' not in page(client)
    [note] = client.get("/api/services").json()
    assert note["description"] == "posted"

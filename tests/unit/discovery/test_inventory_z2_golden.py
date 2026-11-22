"""The inventory built from the full set of outputs captured on the Z2."""
from types import SimpleNamespace

import pytest

from src.services.discovery import SourceError
from src.services.discovery.cgroups import parse_cgroup
from src.services.discovery.docker_ports import parse_docker_ps
from src.services.discovery.firewall import parse_ufw_status
from src.services.discovery.inventory import Sources, build_inventory, collect_snapshot
from src.services.discovery.sockets import parse_ss
from src.services.discovery.tailscale_serve import parse_serve_status
from src.services.discovery.units import UnitStatus

FQDN = "z2.example-tailnet.ts.net"


def annotation(identity_key, **fields):
    values = dict(
        display_name=None,
        description=None,
        hidden=False,
        link_override=None,
        health_path=None,
        primary_port=None,
    )
    values.update(fields)
    return SimpleNamespace(identity_key=identity_key, **values)


# The two entries imported from the old services table.
IMPORTED = [
    annotation("system:finance-tracker.service", description="ABN Amro based finance tracker"),
    annotation("user:1000:ah-connector.service", health_path="/health"),
]


@pytest.fixture
def inventory(fixture_text):
    # cgroups.txt: "<pid> <cgroup line> [process name]"
    cgroup_lines = {}
    for line in fixture_text("cgroups.txt").splitlines():
        if line.strip():
            pid, cgroup_line = line.split()[:2]
            cgroup_lines[int(pid)] = cgroup_line

    def read_cgroup(pid):
        if pid not in cgroup_lines:
            return SourceError("cgroups", f"no cgroup for pid {pid}")
        return parse_cgroup(cgroup_lines[pid])

    sources = Sources(
        list_sockets=lambda: parse_ss(fixture_text("ss-root.txt")),
        read_cgroup=read_cgroup,
        list_published_ports=lambda: parse_docker_ps(fixture_text("docker-ps.jsonl")),
        list_serve_mappings=lambda: parse_serve_status(fixture_text("tailscale-serve.json")),
        read_firewall=lambda: parse_ufw_status(fixture_text("ufw-status.txt")),
        show_unit=lambda unit, uid=None: UnitStatus(
            description="", active_state="active", load_state="loaded"
        ),
    )
    return build_inventory(collect_snapshot(sources), IMPORTED)


def summary(row):
    return row.group, sorted((p.port, p.reach, p.url) for p in row.access_paths)


def test_visible_rows(inventory):
    visible = {row.identity_key: summary(row) for row in inventory.rows if not row.hidden}

    assert visible == {
        "system:finance-tracker.service": (
            "lan",
            [(8001, "lan", None), (8001, "tailnet", f"http://{FQDN}:8001")],
        ),
        "user:1000:groceries-web.service": (
            "tailnet",
            [(8080, "lan_blocked", None), (8080, "tailnet", f"http://{FQDN}:8080")],
        ),
        "user:1000:ntfy.service": (
            "tailnet",
            [(8090, "lan_blocked", None), (8090, "tailnet", f"http://{FQDN}:8090")],
        ),
        "docker:app/app": ("tailnet", [(3000, "tailnet", f"https://{FQDN}:8443/")]),
        "docker:awcp/awcp": ("tailnet", [(8790, "tailnet", f"https://{FQDN}/")]),
        "user:1000:garmin-mcp-proxy.service": ("internal", [(8767, "internal", None)]),
        "user:1000:garmin-mcp-backend.service": ("internal", [(8768, "internal", None)]),
        "user:1000:garmin-mcp-power-proxy.service": ("internal", [(8769, "internal", None)]),
        "user:1000:garmin-mcp-power-backend.service": ("internal", [(8770, "internal", None)]),
        "user:1000:garmin-mcp-rate-limiter.service": ("internal", [(8771, "internal", None)]),
        "user:1000:ah-connector.service": ("internal", [(8772, "internal", None)]),
    }


def test_hidden_rows(inventory):
    hidden = {row.identity_key for row in inventory.rows if row.hidden}

    assert hidden == {
        "system:ssh.service",
        "system:systemd-resolved.service",
        "system:tailscaled.service",
        "system:nginx.service",
        "system:service-registry.service",
        "process:claude",
    }


def test_tailscaled_keeps_only_its_peerapi_ports(inventory):
    row = inventory.row("system:tailscaled.service")

    assert {p.port for p in row.access_paths} == {41563, 51501}


def test_serve_front_ports_are_never_path_ports(inventory):
    ports = {p.port for row in inventory.rows for p in row.access_paths}

    assert ports.isdisjoint({443, 8443, 8765, 8766})


def test_other_processes_are_labelled_with_the_process_name(inventory):
    row = inventory.row("process:claude")

    assert (row.origin, row.display_name, row.group) == ("other", "claude", "internal")


def test_imported_annotations_are_applied(inventory):
    assert (
        inventory.row("system:finance-tracker.service").description
        == "ABN Amro based finance tracker"
    )
    assert inventory.row("user:1000:ah-connector.service").health_path == "/health"


def test_no_link_carries_a_host_address(inventory):
    links = [row.link_override for row in inventory.rows]
    links += [p.link("visitor.example") for row in inventory.rows for p in row.access_paths]

    for link in filter(None, links):
        assert "192.168.2.24" not in link
        assert "127.0.0.1" not in link
        assert "100.65.192.115" not in link


def test_no_source_errors(inventory):
    assert inventory.errors == []

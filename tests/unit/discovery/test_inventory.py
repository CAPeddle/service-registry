"""Tests for turning discovery source results and annotations into page rows."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.repositories.annotation_repository import AnnotationRepository
from src.services.discovery import SourceError
from src.services.discovery.cache import TtlCache
from src.services.discovery.cgroups import Unattributed, UnitRef
from src.services.discovery.docker_ports import Container
from src.services.discovery.firewall import LanFirewall
from src.services.discovery.inventory import (
    InventoryService,
    Sources,
    build_inventory,
    collect_snapshot,
)
from src.services.discovery.sockets import ListeningSocket, SocketProcess
from src.services.discovery.tailscale_serve import ServeMapping
from src.services.discovery.units import UnitStatus

FQDN = "z2.example-tailnet.ts.net"


def sock(address, port, name, pid, interface=None):
    return ListeningSocket(address, port, interface, (SocketProcess(name, pid),))


def system(unit):
    return UnitRef(scope="system", unit=unit, uid=None)


def user(unit, uid=1000):
    return UnitRef(scope="user", unit=unit, uid=uid)


def annotation(identity_key, **fields):
    values = dict(
        display_name=None,
        description=None,
        hidden=None,
        link_override=None,
        health_path=None,
        primary_port=None,
    )
    values.update(fields)
    return SimpleNamespace(identity_key=identity_key, **values)


def make_sources(
    sockets=(),
    cgroups=None,
    docker=None,
    serve=None,
    firewall=None,
    units=None,
):
    """Sources that return the given data; a SourceError value stands for a failed source."""
    cgroups = cgroups or {}
    units = units or {}

    def read_cgroup(pid):
        return cgroups.get(pid, Unattributed("/init.scope"))

    def show_unit(unit, uid=None):
        return units.get(
            (unit, uid), UnitStatus(description="", active_state="active", load_state="loaded")
        )

    return Sources(
        list_sockets=lambda: sockets if isinstance(sockets, SourceError) else list(sockets),
        read_cgroup=read_cgroup,
        list_published_ports=lambda: {} if docker is None else docker,
        list_serve_mappings=lambda: [] if serve is None else serve,
        read_firewall=lambda: LanFirewall(active=True, admitted=())
        if firewall is None
        else firewall,
        show_unit=show_unit,
    )


def inventory_for(annotations=(), **source_data):
    return build_inventory(collect_snapshot(make_sources(**source_data)), annotations)


def paths(row):
    return {(p.port, p.reach, p.url) for p in row.access_paths}


def test_docker_proxy_socket_is_attributed_to_its_container_not_docker_service():
    inventory = inventory_for(
        sockets=[sock("127.0.0.1", 3000, "docker-proxy", 50)],
        cgroups={50: system("docker.service")},
        docker={("127.0.0.1", 3000): Container("app-app-1", "app", "app")},
    )

    keys = [row.identity_key for row in inventory.rows]
    assert keys == ["docker:app/app"]
    row = inventory.row("docker:app/app")
    assert row.origin == "docker"
    assert row.display_name == "app-app-1"


def test_container_without_compose_labels_is_keyed_by_container_name():
    inventory = inventory_for(
        sockets=[sock("127.0.0.1", 9000, "docker-proxy", 50)],
        cgroups={50: system("docker.service")},
        docker={("127.0.0.1", 9000): Container("lonely", None, None)},
    )

    assert [row.identity_key for row in inventory.rows] == ["docker:lonely"]


def test_serve_front_ends_appear_only_as_tailnet_paths_on_their_backend_rows():
    inventory = inventory_for(
        sockets=[
            sock("100.65.192.115", 443, "tailscaled", 7, interface="tailscale0"),
            sock("100.65.192.115", 8443, "tailscaled", 7, interface="tailscale0"),
            sock("127.0.0.1", 8790, "uvicorn", 10),
            sock("127.0.0.1", 3000, "node", 11),
        ],
        cgroups={
            7: system("tailscaled.service"),
            10: system("awcp.service"),
            11: user("clockme.service"),
        },
        serve=[
            ServeMapping(443, f"https://{FQDN}/", "127.0.0.1", 8790),
            ServeMapping(8443, f"https://{FQDN}:8443/", "localhost", 3000),
        ],
    )

    assert {row.identity_key for row in inventory.rows} == {
        "system:awcp.service",
        "user:1000:clockme.service",
    }
    assert paths(inventory.row("system:awcp.service")) == {(8790, "tailnet", f"https://{FQDN}/")}
    assert paths(inventory.row("user:1000:clockme.service")) == {
        (3000, "tailnet", f"https://{FQDN}:8443/")
    }
    assert inventory.row("system:awcp.service").group == "tailnet"


def test_serve_mapping_without_a_listener_produces_no_row():
    inventory = inventory_for(
        sockets=[sock("100.65.192.115", 8765, "tailscaled", 7, interface="tailscale0")],
        cgroups={7: system("tailscaled.service")},
        serve=[ServeMapping(8765, f"http://{FQDN}:8765/", "0.0.0.0", 8766)],
    )

    assert inventory.rows == []


def test_tailscaled_sockets_that_are_not_serve_front_ends_form_a_hidden_row():
    inventory = inventory_for(
        sockets=[sock("100.65.192.115", 51501, "tailscaled", 7, interface="tailscale0")],
        cgroups={7: system("tailscaled.service")},
    )

    row = inventory.row("system:tailscaled.service")
    assert row.hidden and row.suppressed


def test_annotation_can_unhide_a_suppressed_row():
    inventory = inventory_for(
        [annotation("system:tailscaled.service", hidden=False)],
        sockets=[sock("100.65.192.115", 51501, "tailscaled", 7, interface="tailscale0")],
        cgroups={7: system("tailscaled.service")},
    )

    row = inventory.row("system:tailscaled.service")
    assert row.suppressed and not row.hidden


def test_annotation_without_a_hidden_choice_keeps_the_default():
    inventory = inventory_for(
        [annotation("system:tailscaled.service", description="mesh")],
        sockets=[sock("100.65.192.115", 51501, "tailscaled", 7, interface="tailscale0")],
        cgroups={7: system("tailscaled.service")},
    )

    assert inventory.row("system:tailscaled.service").hidden


def test_dual_stack_sockets_on_one_port_collapse_into_one_set_of_paths():
    inventory = inventory_for(
        sockets=[sock("0.0.0.0", 8080, "python", 5), sock("::", 8080, "python", 5)],
        cgroups={5: user("groceries-web.service")},
        serve=[ServeMapping(443, f"https://{FQDN}/", "127.0.0.1", 1)],
    )

    row = inventory.row("user:1000:groceries-web.service")
    assert sorted((p.port, p.reach, p.url) for p in row.access_paths) == [
        (8080, "lan_blocked", None),
        (8080, "tailnet", f"http://{FQDN}:8080"),
    ]


def test_wildcard_bind_without_any_serve_mapping_gets_no_tailnet_path():
    inventory = inventory_for(
        sockets=[sock("0.0.0.0", 8001, "uvicorn", 5)],
        cgroups={5: system("finance-tracker.service")},
        firewall=LanFirewall(active=True, admitted=((8001, 8001),)),
    )

    assert paths(inventory.row("system:finance-tracker.service")) == {(8001, "lan", None)}


def test_lan_path_link_is_built_from_the_visitor_host():
    inventory = inventory_for(
        sockets=[sock("0.0.0.0", 8001, "uvicorn", 5)],
        cgroups={5: system("finance-tracker.service")},
        firewall=LanFirewall(active=True, admitted=((8001, 8001),)),
    )

    (path,) = inventory.row("system:finance-tracker.service").access_paths
    assert path.link("192.168.2.48") == "http://192.168.2.48:8001"


def test_blocked_and_internal_paths_have_no_link():
    inventory = inventory_for(
        sockets=[sock("0.0.0.0", 8080, "python", 5), sock("127.0.0.1", 8772, "ah", 6)],
        cgroups={5: user("groceries-web.service"), 6: user("ah-connector.service")},
    )

    for row in inventory.rows:
        for path in row.access_paths:
            assert path.link("192.168.2.48") is None


def test_interface_scoped_tailnet_bind_is_a_tailnet_path():
    inventory = inventory_for(
        sockets=[sock("100.65.192.115", 9100, "exporter", 5, interface="tailscale0")],
        cgroups={5: system("exporter.service")},
        serve=[ServeMapping(443, f"https://{FQDN}/", "127.0.0.1", 1)],
    )

    row = inventory.row("system:exporter.service")
    assert paths(row) == {(9100, "tailnet", f"http://{FQDN}:9100")}
    assert row.group == "tailnet"


def test_several_ports_make_one_row_with_the_lowest_port_primary():
    inventory = inventory_for(
        sockets=[sock("127.0.0.1", 9001, "app", 5), sock("127.0.0.1", 9000, "app", 5)],
        cgroups={5: system("app.service")},
    )

    row = inventory.row("system:app.service")
    assert row.primary_port == 9000
    assert {(p.port, p.is_primary) for p in row.access_paths} == {(9000, True), (9001, False)}


def test_annotated_primary_port_wins():
    inventory = inventory_for(
        [annotation("system:app.service", primary_port=9001)],
        sockets=[sock("127.0.0.1", 9001, "app", 5), sock("127.0.0.1", 9000, "app", 5)],
        cgroups={5: system("app.service")},
    )

    assert inventory.row("system:app.service").primary_port == 9001


def test_first_process_with_a_unit_attributes_a_shared_socket():
    socket = ListeningSocket(
        "0.0.0.0", 2222, None, (SocketProcess("systemd", 1), SocketProcess("sshd", 9))
    )
    inventory = inventory_for(sockets=[socket], cgroups={9: system("ssh.service")})

    assert [row.identity_key for row in inventory.rows] == ["system:ssh.service"]


def test_unattributable_process_goes_to_hidden_other_processes_named_after_it():
    inventory = inventory_for(sockets=[sock("127.0.0.1", 34729, "claude", 77)])

    row = inventory.row("process:claude")
    assert row.origin == "other"
    assert row.display_name == "claude"
    assert row.hidden


def test_socket_without_process_information_still_gets_a_row():
    inventory = inventory_for(sockets=[ListeningSocket("127.0.0.1", 4000, None, ())])

    assert [row.origin for row in inventory.rows] == ["other"]


def test_display_name_prefers_annotation_then_unit_description():
    inventory = inventory_for(
        [annotation("system:a.service", display_name="Alpha", description="Mine")],
        sockets=[sock("127.0.0.1", 9000, "a", 5), sock("127.0.0.1", 9100, "b", 6)],
        cgroups={5: system("a.service"), 6: system("b.service")},
        units={("b.service", None): UnitStatus("Bravo server", "active", "loaded")},
    )

    alpha = inventory.row("system:a.service")
    assert (alpha.display_name, alpha.description) == ("Alpha", "Mine")
    assert inventory.row("system:b.service").display_name == "Bravo server"


def test_annotation_fields_are_carried_onto_the_row():
    inventory = inventory_for(
        [annotation("user:1000:ah.service", health_path="/health", link_override="http://x/")],
        sockets=[sock("127.0.0.1", 8772, "ah", 5)],
        cgroups={5: user("ah.service")},
    )

    row = inventory.row("user:1000:ah.service")
    assert (row.health_path, row.link_override) == ("/health", "http://x/")
    assert row.state == "running"


def test_annotation_hidden_flag_hides_a_row():
    inventory = inventory_for(
        [annotation("system:app.service", hidden=True)],
        sockets=[sock("127.0.0.1", 9000, "app", 5)],
        cgroups={5: system("app.service")},
    )

    row = inventory.row("system:app.service")
    assert row.hidden and not row.suppressed


@pytest.mark.parametrize(
    "active_state, load_state, expected",
    [
        ("failed", "loaded", "failed"),
        ("inactive", "loaded", "inactive"),
        ("active", "loaded", "running without a port"),
        ("inactive", "not-found", "not found"),
    ],
)
def test_annotated_unit_without_a_listener_shows_its_unit_state(active_state, load_state, expected):
    inventory = inventory_for(
        [annotation("system:gone.service"), annotation("user:1000:gone.service")],
        units={
            ("gone.service", None): UnitStatus("Gone", active_state, load_state),
            ("gone.service", 1000): UnitStatus("Gone", active_state, load_state),
        },
    )

    for key in ("system:gone.service", "user:1000:gone.service"):
        row = inventory.row(key)
        assert (row.state, row.group, row.access_paths) == (expected, "not_running", ())


def test_unit_lookup_failure_for_a_not_running_row_is_unknown_and_reported():
    inventory = inventory_for(
        [annotation("system:gone.service")],
        units={("gone.service", None): SourceError("units", "systemctl exited 1")},
    )

    assert inventory.row("system:gone.service").state == "unknown"
    assert [e.source for e in inventory.errors] == ["units"]


def test_manual_identity_shows_its_link_override_with_unknown_state():
    inventory = inventory_for([annotation("manual:printer", link_override="http://printer.lan/")])

    row = inventory.row("manual:printer")
    assert (row.origin, row.state, row.link_override) == (
        "manual",
        "unknown",
        "http://printer.lan/",
    )
    assert row.display_name == "printer"


def test_docker_identity_without_a_listener_is_not_running():
    inventory = inventory_for([annotation("docker:media/plex")])

    row = inventory.row("docker:media/plex")
    assert (row.state, row.group) == ("not running", "not_running")


def test_annotated_other_process_without_a_listener_gets_no_row():
    inventory = inventory_for([annotation("process:claude", hidden=True)])

    assert inventory.rows == []


def test_tailscale_failure_makes_loopback_rows_unknown_and_is_reported():
    error = SourceError("tailscale", "tailscale exited 1")
    inventory = inventory_for(
        sockets=[sock("127.0.0.1", 8772, "ah", 5)],
        cgroups={5: user("ah.service")},
        serve=error,
    )

    row = inventory.row("user:1000:ah.service")
    assert paths(row) == {(8772, "unknown", None)}
    assert row.group == "unknown"
    assert inventory.errors == [error]


def test_docker_failure_makes_docker_proxy_sockets_unknown_not_docker_service():
    inventory = inventory_for(
        sockets=[sock("127.0.0.1", 3000, "docker-proxy", 50)],
        cgroups={50: system("docker.service")},
        docker=SourceError("docker", "command not found: docker"),
    )

    (row,) = inventory.rows
    assert row.identity_key != "system:docker.service"
    assert row.origin == "docker"
    assert paths(row) == {(3000, "unknown", None)}
    assert row.group == "unknown"
    assert [e.source for e in inventory.errors] == ["docker"]


def test_firewall_failure_makes_wildcard_lan_paths_unknown():
    inventory = inventory_for(
        sockets=[sock("0.0.0.0", 8080, "python", 5)],
        cgroups={5: user("groceries-web.service")},
        serve=[ServeMapping(443, f"https://{FQDN}/", "127.0.0.1", 1)],
        firewall=SourceError("firewall", "ufw exited 1"),
    )

    row = inventory.row("user:1000:groceries-web.service")
    assert paths(row) == {(8080, "unknown", None), (8080, "tailnet", f"http://{FQDN}:8080")}
    assert row.group == "unknown"


@pytest.mark.parametrize(
    "firewall",
    [
        LanFirewall(active=True, admitted=()),
        SourceError("firewall", "ufw exited 1"),
    ],
)
def test_docker_published_wildcard_port_skips_the_firewall(firewall):
    inventory = inventory_for(
        sockets=[sock("0.0.0.0", 8080, "docker-proxy", 50)],
        cgroups={50: system("docker.service")},
        docker={("0.0.0.0", 8080): Container("web-web-1", "web", "web")},
        firewall=firewall,
    )

    assert paths(inventory.row("docker:web/web")) == {(8080, "lan", None)}
    assert inventory.row("docker:web/web").group == "lan"


def test_socket_failure_shows_annotated_services_as_unknown_not_stopped():
    error = SourceError("sockets", "ss timed out after 2s")
    inventory = inventory_for([annotation("system:app.service")], sockets=error)

    row = inventory.row("system:app.service")
    assert (row.state, row.group) == ("unknown", "unknown")
    assert inventory.errors == [error]


def test_repeated_unit_failures_are_reported_once_per_source():
    inventory = inventory_for(
        [annotation("system:a.service"), annotation("system:b.service")],
        units={
            ("a.service", None): SourceError("units", "a failed"),
            ("b.service", None): SourceError("units", "b failed"),
        },
    )

    assert [e.source for e in inventory.errors] == ["units"]


class CountingSources:
    """Sources whose every call is counted."""

    def __init__(self):
        self.calls = 0
        base = make_sources(
            sockets=[sock("127.0.0.1", 9000, "app", 5)],
            cgroups={5: system("app.service")},
        )
        self.sources = Sources(
            **{
                name: self._counted(getattr(base, name))
                for name in (
                    "list_sockets",
                    "read_cgroup",
                    "list_published_ports",
                    "list_serve_mappings",
                    "read_firewall",
                    "show_unit",
                )
            }
        )

    def _counted(self, fn):
        def wrapper(*args, **kwargs):
            self.calls += 1
            return fn(*args, **kwargs)

        return wrapper


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield AnnotationRepository(session)
    session.close()


def make_service(counting, clock, repo):
    cache = TtlCache(lambda: collect_snapshot(counting.sources), ttl=10.0, clock=clock)
    return InventoryService(cache, repo)


def test_second_call_within_the_cache_window_does_not_rerun_sources(repo):
    counting, clock = CountingSources(), FakeClock()
    service = make_service(counting, clock, repo)

    service.get()
    calls_after_first = counting.calls
    clock.now += 9
    service.get()

    assert calls_after_first > 0
    assert counting.calls == calls_after_first


def test_refresh_flag_reruns_sources(repo):
    counting, clock = CountingSources(), FakeClock()
    service = make_service(counting, clock, repo)

    service.get()
    calls_after_first = counting.calls
    service.get(refresh=True)

    assert counting.calls == 2 * calls_after_first


def test_sources_rerun_after_the_cache_window(repo):
    counting, clock = CountingSources(), FakeClock()
    service = make_service(counting, clock, repo)

    service.get()
    calls_after_first = counting.calls
    clock.now += 11
    service.get()

    assert counting.calls == 2 * calls_after_first


def test_unit_lookups_for_new_annotations_are_cached_with_the_sources(repo):
    counting, clock = CountingSources(), FakeClock()
    service = make_service(counting, clock, repo)
    repo.upsert("system:gone.service", description="x")

    service.get()
    calls_after_first = counting.calls
    service.get()

    assert counting.calls == calls_after_first


def test_annotation_edit_between_cached_calls_is_visible(repo):
    counting, clock = CountingSources(), FakeClock()
    service = make_service(counting, clock, repo)

    service.get()
    repo.upsert("system:app.service", display_name="My App", hidden=True)
    row = service.get().row("system:app.service")

    assert (row.display_name, row.hidden) == ("My App", True)


def test_inventory_provider_shares_one_source_cache_across_requests(repo):
    from src.api.dependencies.services import get_inventory_service

    first = get_inventory_service(repo.session)
    second = get_inventory_service(repo.session)

    assert isinstance(first, InventoryService)
    assert first.cache is second.cache


def test_bind_on_the_lan_address_gets_a_lan_path_without_a_tailnet_path():
    inventory = inventory_for(
        sockets=[sock("192.168.2.48", 9000, "app", 5)],
        cgroups={5: system("app.service")},
        serve=[ServeMapping(443, f"https://{FQDN}/", "127.0.0.1", 1)],
        firewall=LanFirewall(active=True, admitted=((9000, 9000),)),
    )

    assert paths(inventory.row("system:app.service")) == {(9000, "lan", None)}


def test_unit_lookup_failure_for_a_running_row_falls_back_to_the_unit_name():
    inventory = inventory_for(
        sockets=[sock("127.0.0.1", 9000, "app", 5)],
        cgroups={5: user("app.service")},
        units={("app.service", 1000): SourceError("units", "no user with uid 1000")},
    )

    assert inventory.row("user:1000:app.service").display_name == "app.service"
    assert [e.source for e in inventory.errors] == ["units"]


def test_malformed_user_identity_without_a_listener_gets_no_row():
    inventory = inventory_for([annotation("user:nobody")])

    assert inventory.rows == []


def test_docker_failure_shows_annotated_containers_as_unknown_not_stopped():
    inventory = inventory_for(
        [annotation("docker:app/app", display_name="clockme")],
        sockets=[sock("127.0.0.1", 3000, "docker-proxy", 50)],
        cgroups={50: system("docker.service")},
        docker=SourceError("docker", "command not found: docker"),
    )

    row = inventory.row("docker:app/app")
    assert (row.state, row.group) == ("unknown", "unknown")

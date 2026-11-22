"""Tests for the listening-socket source (ss)."""
import pytest

from src.services.discovery import SourceError
from src.services.discovery.sockets import (
    SOURCE,
    ListeningSocket,
    SocketProcess,
    list_sockets,
    parse_ss,
)


@pytest.fixture
def sockets(fixture_text):
    return parse_ss(fixture_text("ss-root.txt"))


def _on_port(sockets, port):
    return [s for s in sockets if s.port == port]


def test_parses_every_captured_line(sockets, fixture_text):
    assert len(sockets) == len(fixture_text("ss-root.txt").strip().splitlines())


def test_ipv4_wildcard_bind_with_pid(sockets):
    assert _on_port(sockets, 8001) == [
        ListeningSocket(
            address="0.0.0.0",
            port=8001,
            interface=None,
            processes=(SocketProcess(name="uvicorn", pid=1128646),),
        )
    ]


def test_star_bind(sockets):
    [ntfy] = _on_port(sockets, 8090)
    assert ntfy.address == "*"
    assert ntfy.pids == (1788,)


def test_loopback_bind_of_user_unit_listener(sockets):
    [connector] = _on_port(sockets, 8772)
    assert connector.address == "127.0.0.1"
    assert connector.pids == (1622,)


def test_both_families_on_port_80_keep_every_nginx_pid(sockets):
    by_address = {s.address: s for s in _on_port(sockets, 80)}
    assert set(by_address) == {"0.0.0.0", "::"}
    expected = (1854891, 1854890, 1854889, 1854888, 1854887, 1854886, 1854884)
    assert by_address["0.0.0.0"].pids == expected
    assert by_address["::"].pids == expected
    assert {p.name for p in by_address["::"].processes} == {"nginx"}


def test_several_processes_on_one_socket_are_all_kept(sockets):
    ipv4_ssh = [s for s in _on_port(sockets, 22) if s.address == "0.0.0.0"]
    assert ipv4_ssh[0].processes == (
        SocketProcess(name="sshd", pid=1854885),
        SocketProcess(name="systemd", pid=1),
    )


def test_interface_scoped_ipv4_bind(sockets):
    v4 = [s for s in _on_port(sockets, 8443) if ":" not in s.address]
    assert v4 == [
        ListeningSocket(
            address="100.65.192.115",
            port=8443,
            interface="tailscale0",
            processes=(SocketProcess(name="tailscaled", pid=1611223),),
        )
    ]


def test_interface_scoped_ipv6_bind_has_brackets_stripped(sockets):
    v6 = [s for s in _on_port(sockets, 443) if ":" in s.address]
    assert [(s.address, s.interface) for s in v6] == [
        ("fd7a:115c:a1e0::5536:c074", "tailscale0")
    ]


def test_loopback_scoped_resolver(sockets):
    scoped = [s for s in _on_port(sockets, 53) if s.interface == "lo"]
    assert [s.address for s in scoped] == ["127.0.0.53"]


def test_line_without_users_section_has_no_pid(fixture_text):
    sockets = parse_ss(fixture_text("ss-user.txt"))
    [nginx_v4] = [s for s in sockets if s.port == 80 and s.address == "0.0.0.0"]
    assert nginx_v4.pids == ()
    assert nginx_v4.processes == ()


def test_blank_output_yields_no_sockets():
    assert parse_ss("") == []


def test_runner_parses_command_output(fixture_text, tmp_path):
    path = tmp_path / "ss.txt"
    path.write_text(fixture_text("ss-root.txt"))
    result = list_sockets(argv=("cat", str(path)))
    assert isinstance(result, list)
    assert any(s.port == 8001 for s in result)


def test_runner_errors_name_the_source(slow_command):
    for result in (
        list_sockets(argv=("/nonexistent/ss",)),
        list_sockets(argv=("false",)),
        list_sockets(argv=(slow_command,), timeout=0.2),
    ):
        assert isinstance(result, SourceError)
        assert result.source == SOURCE

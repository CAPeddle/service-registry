"""Tests for the LAN firewall source (ufw)."""
import pytest

from src.services.discovery import SourceError
from src.services.discovery.firewall import (
    SOURCE,
    parse_ufw_status,
    read_firewall,
)

HEADER = """Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), deny (routed)
New profiles: skip

To                         Action      From
--                         ------      ----
"""


@pytest.fixture
def firewall(fixture_text):
    return parse_ufw_status(fixture_text("ufw-status.txt"))


def test_port_with_lan_interface_rule_is_admitted(firewall):
    assert firewall.admits_lan(8001) is True


@pytest.mark.parametrize("port", [80, 8080, 8090])
def test_ports_without_rules_are_not_admitted(firewall, port):
    assert firewall.admits_lan(port) is False


def test_rule_on_tailnet_interface_does_not_admit_lan(firewall):
    assert firewall.admits_lan(22) is False


def test_udp_rule_does_not_admit_tcp(firewall):
    assert firewall.admits_lan(41641) is False


def test_lan_interface_is_a_parameter(fixture_text):
    firewall = parse_ufw_status(fixture_text("ufw-status.txt"), lan_interface="wlan0")
    assert firewall.admits_lan(8001) is False


def test_rule_without_interface_from_lan_subnet_admits():
    assert parse_ufw_status(HEADER + "80/tcp ALLOW IN 192.168.2.0/24\n").admits_lan(80) is True


def test_rule_without_interface_from_anywhere_admits():
    assert parse_ufw_status(HEADER + "8080/tcp   ALLOW IN    Anywhere\n").admits_lan(8080) is True


def test_rule_from_single_lan_host_admits():
    assert parse_ufw_status(HEADER + "8090/tcp ALLOW IN 192.168.2.20\n").admits_lan(8090) is True


def test_rule_from_other_subnet_does_not_admit():
    assert parse_ufw_status(HEADER + "8090/tcp ALLOW IN 10.0.0.0/8\n").admits_lan(8090) is False


def test_v6_rule_does_not_admit_ipv4_lan():
    firewall = parse_ufw_status(HEADER + "8080/tcp (v6) ALLOW IN Anywhere (v6)\n")
    assert firewall.admits_lan(8080) is False


def test_rule_without_protocol_covers_tcp():
    assert parse_ufw_status(HEADER + "8085 ALLOW IN Anywhere\n").admits_lan(8085) is True


def test_port_range_and_comment():
    firewall = parse_ufw_status(
        HEADER + "60000:60010/tcp on eno1 ALLOW IN 192.168.2.0/24   # dev servers\n"
    )
    assert firewall.admits_lan(60005) is True
    assert firewall.admits_lan(60011) is False


def test_rule_for_every_port_from_lan_admits_any_port():
    firewall = parse_ufw_status(HEADER + "Anywhere on eno1           ALLOW IN    192.168.2.0/24\n")
    assert firewall.admits_lan(8090) is True


def test_lan_subnet_is_a_parameter(fixture_text):
    firewall = parse_ufw_status(fixture_text("ufw-status.txt"), lan_subnet="192.168.50.0/24")
    assert firewall.admits_lan(8001) is False


def test_outbound_and_forward_rules_do_not_admit():
    firewall = parse_ufw_status(HEADER + "80/tcp ALLOW OUT Anywhere\n81/tcp ALLOW FWD Anywhere\n")
    assert firewall.admits_lan(80) is False
    assert firewall.admits_lan(81) is False


def test_rate_limited_rule_admits():
    assert parse_ufw_status(HEADER + "8086/tcp LIMIT IN Anywhere\n").admits_lan(8086) is True


def test_rule_listing_several_ports():
    firewall = parse_ufw_status(HEADER + "80,443/tcp ALLOW IN Anywhere\n")
    assert firewall.admits_lan(80) is True
    assert firewall.admits_lan(443) is True
    assert firewall.admits_lan(8080) is False


def test_rule_without_direction_counts_as_inbound():
    assert parse_ufw_status(HEADER + "8087/tcp ALLOW Anywhere\n").admits_lan(8087) is True


def test_deny_rule_does_not_admit():
    assert parse_ufw_status(HEADER + "80/tcp DENY IN Anywhere\n").admits_lan(80) is False


def test_inactive_firewall_admits_every_port():
    firewall = parse_ufw_status("Status: inactive\n")
    assert firewall.admits_lan(80) is True
    assert firewall.admits_lan(22) is True


def test_output_without_status_line_is_an_error():
    with pytest.raises(ValueError):
        parse_ufw_status("ERROR: You need to be root to run this script\n")


def test_runner_parses_command_output(fixture_text, tmp_path):
    path = tmp_path / "ufw.txt"
    path.write_text(fixture_text("ufw-status.txt"))
    result = read_firewall(argv=("cat", str(path)))
    assert result.admits_lan(8001) is True
    assert result.admits_lan(80) is False


def test_runner_error_on_output_without_status_line():
    result = read_firewall(argv=("echo", "something else"))
    assert isinstance(result, SourceError)
    assert result.source == SOURCE


def test_runner_errors_name_the_source(slow_command):
    for result in (
        read_firewall(argv=("/nonexistent/ufw",)),
        read_firewall(argv=("false",)),
        read_firewall(argv=(slow_command,), timeout=0.2),
    ):
        assert isinstance(result, SourceError)
        assert result.source == SOURCE

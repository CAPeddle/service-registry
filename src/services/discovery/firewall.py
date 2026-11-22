"""Whether ufw admits LAN traffic to a TCP port, from ``ufw status verbose``.

A port is admitted when some ALLOW (or LIMIT) IN rule covers TCP on that port,
is IPv4, applies on the LAN interface (or on no specific interface), and comes
from ``Anywhere`` or an address range overlapping the LAN subnet. Rule order
and DENY rules are not evaluated. Rules naming an application profile or a
destination address are not counted. ``ufw status`` needs root.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Sequence

from . import DEFAULT_TIMEOUT, SourceError, run_source

SOURCE = "firewall"
UFW_ARGV = ("ufw", "status", "verbose")
DEFAULT_LAN_INTERFACE = "eno1"
DEFAULT_LAN_SUBNET = "192.168.2.0/24"

# Split on the action rather than on columns: a long To such as
# "8001/tcp (v6) on tailscale0" runs into the Action column.
_RULE = re.compile(r"^(?P<to>.+?)\s+(?P<action>ALLOW|DENY|REJECT|LIMIT)(?:\s+(?P<direction>IN|OUT|FWD))?\s+(?P<source>.+)$")
_PORTS = re.compile(r"^(?P<ports>[\d,:]+)(?:/(?P<proto>tcp|udp))?$")


@dataclass(frozen=True)
class LanFirewall:
    active: bool
    admitted: tuple[tuple[int, int], ...]  # inclusive TCP port ranges

    def admits_lan(self, port: int) -> bool:
        if not self.active:
            return True
        return any(low <= port <= high for low, high in self.admitted)


def parse_ufw_status(
    text: str,
    *,
    lan_interface: str = DEFAULT_LAN_INTERFACE,
    lan_subnet: str = DEFAULT_LAN_SUBNET,
) -> LanFirewall:
    status = None
    admitted: list[tuple[int, int]] = []
    lan = ipaddress.ip_network(lan_subnet)
    for line in text.splitlines():
        if line.startswith("Status:"):
            status = line.split(":", 1)[1].strip()
            continue
        match = _RULE.match(line.split("#", 1)[0].strip())
        if not match or match["action"] not in ("ALLOW", "LIMIT"):
            continue
        if match["direction"] not in (None, "IN"):
            continue
        ranges = _admitted_ranges(match["to"].split(), match["source"].split(), lan_interface, lan)
        admitted.extend(ranges)

    if status is None:
        raise ValueError("no 'Status:' line in ufw output")
    return LanFirewall(active=status != "inactive", admitted=tuple(admitted))


def _admitted_ranges(
    to: list[str],
    source: list[str],
    lan_interface: str,
    lan: ipaddress.IPv4Network | ipaddress.IPv6Network,
) -> list[tuple[int, int]]:
    if "(v6)" in to or "(v6)" in source:
        return []
    if "on" in to:
        index = to.index("on")
        if to[index + 1:index + 2] != [lan_interface]:
            return []
        to = to[:index] + to[index + 2:]
    if len(to) != 1 or not _from_lan(source[0] if source else "", lan):
        return []
    if to[0] == "Anywhere":
        return [(1, 65535)]
    ports = _PORTS.match(to[0])
    if not ports or ports["proto"] == "udp":
        return []
    ranges = []
    for part in ports["ports"].split(","):
        low, _, high = part.partition(":")
        if low.isdigit() and (high.isdigit() or not high):
            ranges.append((int(low), int(high or low)))
    return ranges


def _from_lan(source: str, lan: ipaddress.IPv4Network | ipaddress.IPv6Network) -> bool:
    if source == "Anywhere":
        return True
    try:
        network = ipaddress.ip_network(source, strict=False)
    except ValueError:
        return False
    return network.version == lan.version and network.overlaps(lan)


def read_firewall(
    *,
    argv: Sequence[str] = UFW_ARGV,
    timeout: float = DEFAULT_TIMEOUT,
    lan_interface: str = DEFAULT_LAN_INTERFACE,
    lan_subnet: str = DEFAULT_LAN_SUBNET,
) -> LanFirewall | SourceError:
    def parse(text: str) -> LanFirewall:
        return parse_ufw_status(text, lan_interface=lan_interface, lan_subnet=lan_subnet)

    return run_source(SOURCE, argv, parse, timeout)

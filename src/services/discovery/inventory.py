"""The live inventory: discovery source results plus annotations, as page rows.

Every listening socket is attributed to one identity, in this order:

1. A docker-proxy socket belongs to the container that publishes its port
   (``docker:<project>/<service>``, else ``docker:<container name>``). Without
   the Docker source it becomes an unknown row of its own, never
   ``docker.service``.
2. A tailscaled socket on a Tailscale serve front port is not a row. The serve
   URL becomes a tailnet access path on whichever row listens on the mapping's
   target port (joined on port only), and a mapping nobody listens behind
   produces nothing.
3. Otherwise the first of the socket's processes whose cgroup names a unit
   gives ``system:<unit>`` or ``user:<uid>:<unit>``.
4. Anything left over is an "other process", keyed ``process:<name>``.

Each bind address then yields access paths. A wildcard bind gets a LAN path
(admitted, blocked by the firewall, or unknown when the firewall source
failed; Docker-published ports skip the firewall) and, when the tailnet name
is known from a serve URL, a direct tailnet path. A bind on the tailnet is a
tailnet path. Any other single-address bind (loopback, bridge, link-local) is
internal unless serve fronts its port, and unknown when the Tailscale source
failed. LAN paths carry no URL: the page builds them from the visitor's host.

A row is hidden when its annotation says so. An annotation that leaves
``hidden`` unset falls back to the default: hidden only when the row is on the
suppression list. So the user can hide any row and unhide a suppressed one.
"""
from __future__ import annotations

import ipaddress
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Protocol
from urllib.parse import urlsplit

from . import SourceError, cgroups, docker_ports, firewall, sockets, tailscale_serve, units
from .cache import TtlCache
from .cgroups import Unattributed, UnitRef
from .docker_ports import Container
from .firewall import LanFirewall
from .sockets import ListeningSocket
from .tailscale_serve import ServeMapping
from .units import UnitStatus

# How an access path reaches the service.
LAN = "lan"
LAN_BLOCKED = "lan_blocked"
TAILNET = "tailnet"
INTERNAL = "internal"
UNKNOWN = "unknown"

# Where a row is placed on the page. Running rows take the group of their best
# working path; any unknown path puts a row in the unknown group.
GROUP_UNKNOWN = "unknown"
GROUP_LAN = "lan"
GROUP_TAILNET = "tailnet"
GROUP_INTERNAL = "internal"
GROUP_NOT_RUNNING = "not_running"

RUNNING = "running"

_WILDCARDS = frozenset({"0.0.0.0", "::", "*"})
_TAILNET_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
_TAILNET_INTERFACE = "tailscale0"
_LAN_NETWORK = ipaddress.ip_network(firewall.DEFAULT_LAN_SUBNET)

# Default suppression list.
_NOISE_PORTS = frozenset({22, 53})
_NOISE_PORTS_BY_IDENTITY = {
    "system:nginx.service": frozenset({80}),
    "system:service-registry.service": frozenset({8000}),  # this app
}
_TAILSCALED_KEY = "system:tailscaled.service"  # what remains are its peerapi ports


@dataclass(frozen=True)
class Sources:
    """The discovery sources, swappable so tests can feed captured output."""

    list_sockets: Callable[[], list[ListeningSocket] | SourceError] = sockets.list_sockets
    read_cgroup: Callable[[int], UnitRef | Unattributed | SourceError] = cgroups.read_cgroup
    list_published_ports: Callable[[], dict[tuple[str, int], Container] | SourceError] = (
        docker_ports.list_published_ports)
    list_serve_mappings: Callable[[], list[ServeMapping] | SourceError] = tailscale_serve.list_serve_mappings
    read_firewall: Callable[[], LanFirewall | SourceError] = firewall.read_firewall
    show_unit: Callable[[str, int | None], UnitStatus | SourceError] = units.show_unit


@dataclass
class SourceSnapshot:
    """One read of every source. Unit statuses are fetched on first use and kept with it."""

    sockets: list[ListeningSocket] | SourceError
    cgroups: dict[int, UnitRef | Unattributed | SourceError]
    docker: dict[tuple[str, int], Container] | SourceError
    serve: list[ServeMapping] | SourceError
    firewall: LanFirewall | SourceError
    show_unit: Callable[[str, int | None], UnitStatus | SourceError]
    _units: dict[tuple[str, int | None], UnitStatus | SourceError] = field(default_factory=dict)

    def unit_status(self, unit: str, uid: int | None) -> UnitStatus | SourceError:
        key = (unit, uid)
        if key not in self._units:
            self._units[key] = self.show_unit(unit, uid)
        return self._units[key]


def collect_snapshot(sources: Sources) -> SourceSnapshot:
    listening = sources.list_sockets()
    pids = set() if isinstance(listening, SourceError) else {pid for s in listening for pid in s.pids}
    return SourceSnapshot(
        sockets=listening,
        cgroups={pid: sources.read_cgroup(pid) for pid in sorted(pids)},
        docker=sources.list_published_ports(),
        serve=sources.list_serve_mappings(),
        firewall=sources.read_firewall(),
        show_unit=sources.show_unit,
    )


@dataclass(frozen=True)
class AccessPath:
    """One way to reach a service.

    ``port`` is the local listening port (the one to probe), even when ``url``
    is a Tailscale serve URL on another front port. ``url`` is set for tailnet
    paths only.
    """

    port: int
    reach: str
    url: str | None
    is_primary: bool

    def link(self, visitor_host: str) -> str | None:
        """The URL to offer a visitor who browsed to ``visitor_host``."""
        if self.url:
            return self.url
        if self.reach == LAN:
            return f"http://{visitor_host}:{self.port}"
        return None


@dataclass(frozen=True)
class InventoryRow:
    identity_key: str
    display_name: str
    description: str | None
    origin: str  # system, user, docker, manual or other
    state: str  # running, running without a port, failed, inactive, not found, not running, unknown, ...
    group: str
    hidden: bool
    suppressed: bool  # on the default suppression list
    access_paths: tuple[AccessPath, ...]
    primary_port: int | None
    health_path: str | None
    link_override: str | None


@dataclass
class Inventory:
    rows: list[InventoryRow]
    errors: list[SourceError]  # at most one per failed source

    def row(self, identity_key: str) -> InventoryRow | None:
        return next((r for r in self.rows if r.identity_key == identity_key), None)


class AnnotationSource(Protocol):
    def list(self) -> Iterable[Any]: ...


class InventoryService:
    """Builds the inventory from cached source results and freshly read annotations."""

    def __init__(self, cache: TtlCache[SourceSnapshot], annotations: AnnotationSource):
        self.cache = cache
        self.annotations = annotations

    def get(self, *, refresh: bool = False) -> Inventory:
        return build_inventory(self.cache.get(refresh=refresh), self.annotations.list())


shared_source_cache: TtlCache[SourceSnapshot] = TtlCache(lambda: collect_snapshot(Sources()))


@dataclass
class _Identity:
    key: str
    origin: str
    name: str
    unit: UnitRef | None = None
    docker_published: bool = False
    unresolved: bool = False  # a docker-proxy socket whose container is unknown


@dataclass
class _Draft:
    identity: _Identity
    paths: list[tuple[int, str, str | None]] = field(default_factory=list)


def build_inventory(snapshot: SourceSnapshot, annotations: Iterable[Any]) -> Inventory:
    errors: dict[str, SourceError] = {}
    for result in (snapshot.sockets, snapshot.docker, snapshot.serve, snapshot.firewall):
        if isinstance(result, SourceError):
            errors.setdefault(result.source, result)

    by_key = {a.identity_key: a for a in annotations}
    context = _Context(snapshot)

    drafts: dict[str, _Draft] = {}
    listening = [] if isinstance(snapshot.sockets, SourceError) else snapshot.sockets
    for socket in listening:
        if context.is_serve_front(socket):
            continue
        identity = context.attribute(socket)
        draft = drafts.setdefault(identity.key, _Draft(identity))
        draft.paths.extend(context.classify(socket, identity))

    rows = [_running_row(d, by_key.get(key), snapshot, errors) for key, d in drafts.items()]
    for key, note in by_key.items():
        if key not in drafts:
            row = _absent_row(key, note, snapshot, errors)
            if row is not None:
                rows.append(row)

    rows.sort(key=lambda r: (r.display_name.lower(), r.identity_key))
    return Inventory(rows=rows, errors=list(errors.values()))


class _Context:
    """Source results arranged for attributing and classifying sockets."""

    def __init__(self, snapshot: SourceSnapshot):
        self.snapshot = snapshot
        self.docker = None if isinstance(snapshot.docker, SourceError) else snapshot.docker
        self.serve_ok = not isinstance(snapshot.serve, SourceError)
        self.firewall = None if isinstance(snapshot.firewall, SourceError) else snapshot.firewall
        mappings = snapshot.serve if self.serve_ok else []
        self.front_ports = {m.front_port for m in mappings}
        self.fronts: dict[int, list[str]] = defaultdict(list)
        for mapping in mappings:
            self.fronts[mapping.target_port].append(mapping.url)
        self.fqdn = next((urlsplit(m.url).hostname for m in mappings if urlsplit(m.url).hostname), None)

    def is_serve_front(self, socket: ListeningSocket) -> bool:
        return socket.port in self.front_ports and any(p.name == "tailscaled" for p in socket.processes)

    def attribute(self, socket: ListeningSocket) -> _Identity:
        if any(p.name == "docker-proxy" for p in socket.processes):
            container = self._container(socket)
            if container is None:
                return _Identity(f"docker-proxy:{socket.port}", "docker", "docker-proxy", unresolved=True)
            if container.project and container.service:
                key = f"docker:{container.project}/{container.service}"
            else:
                key = f"docker:{container.name}"
            return _Identity(key, "docker", container.name, docker_published=True)

        for process in socket.processes:
            ref = self.snapshot.cgroups.get(process.pid)
            if isinstance(ref, UnitRef):
                key = f"system:{ref.unit}" if ref.scope == "system" else f"user:{ref.uid}:{ref.unit}"
                return _Identity(key, ref.scope, ref.unit, unit=ref)

        name = socket.processes[0].name if socket.processes else "unknown process"
        return _Identity(f"process:{name}", "other", name)

    def _container(self, socket: ListeningSocket) -> Container | None:
        if self.docker is None:
            return None
        return self.docker.get((socket.address, socket.port))

    def classify(self, socket: ListeningSocket, identity: _Identity) -> list[tuple[int, str, str | None]]:
        port = socket.port
        if identity.unresolved:
            return [(port, UNKNOWN, None)]

        paths: list[tuple[int, str, str | None]] = []
        address = _ip(socket.address)
        if socket.address in _WILDCARDS:
            paths.append((port, self._lan_reach(port, identity), None))
            if self.fqdn:
                paths.append((port, TAILNET, f"http://{self.fqdn}:{port}"))
        elif socket.interface == _TAILNET_INTERFACE or any(address in n for n in _TAILNET_NETWORKS if address):
            paths.append((port, TAILNET, f"http://{self.fqdn}:{port}" if self.fqdn else None))
        elif address is not None and address in _LAN_NETWORK:
            paths.append((port, self._lan_reach(port, identity), None))
        elif not self.serve_ok:
            paths.append((port, UNKNOWN, None))
        elif not self.fronts.get(port):
            paths.append((port, INTERNAL, None))
        paths.extend((port, TAILNET, url) for url in self.fronts.get(port, []))
        return paths

    def _lan_reach(self, port: int, identity: _Identity) -> str:
        if identity.docker_published:  # Docker's DNAT bypasses ufw
            return LAN
        if self.firewall is None:
            return UNKNOWN
        return LAN if self.firewall.admits_lan(port) else LAN_BLOCKED


def _ip(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(address)
    except ValueError:
        return None


def _running_row(
    draft: _Draft,
    note: Any | None,
    snapshot: SourceSnapshot,
    errors: dict[str, SourceError],
) -> InventoryRow:
    identity = draft.identity
    ports = sorted({port for port, _, _ in draft.paths})
    primary = note.primary_port if note is not None and note.primary_port in ports else ports[0]

    unique = list(dict.fromkeys(draft.paths))
    unique.sort(key=lambda path: path[0])
    paths = tuple(AccessPath(port, reach, url, port == primary) for port, reach, url in unique)

    suppressed = identity.origin == "other" or all(_is_noise(identity.key, port) for port in ports)
    name = _annotated(note, "display_name")
    if not name and identity.unit is not None:
        status = snapshot.unit_status(identity.unit.unit, identity.unit.uid)
        if isinstance(status, SourceError):
            errors.setdefault(status.source, status)
        else:
            name = status.description

    return InventoryRow(
        identity_key=identity.key,
        display_name=name or identity.name,
        description=_annotated(note, "description"),
        origin=identity.origin,
        state=RUNNING,
        group=_group(paths),
        hidden=_hidden(note, suppressed),
        suppressed=suppressed,
        access_paths=paths,
        primary_port=primary,
        health_path=_annotated(note, "health_path"),
        link_override=_annotated(note, "link_override"),
    )


def _is_noise(key: str, port: int) -> bool:
    return port in _NOISE_PORTS or key == _TAILSCALED_KEY or port in _NOISE_PORTS_BY_IDENTITY.get(key, ())


def _group(paths: tuple[AccessPath, ...]) -> str:
    reaches = {path.reach for path in paths}
    if UNKNOWN in reaches:
        return GROUP_UNKNOWN
    if LAN in reaches:
        return GROUP_LAN
    if TAILNET in reaches:
        return GROUP_TAILNET
    return GROUP_INTERNAL


def _absent_row(
    key: str,
    note: Any,
    snapshot: SourceSnapshot,
    errors: dict[str, SourceError],
) -> InventoryRow | None:
    """A row for an annotated identity that has no listening socket."""
    origin, _, rest = key.partition(":")
    unit: tuple[str, int | None] | None = None
    if origin == "system":
        unit, name = (rest, None), rest
    elif origin == "user":
        uid, _, unit_name = rest.partition(":")
        if not uid.isdigit() or not unit_name:
            return None
        unit, name = (unit_name, int(uid)), unit_name
    elif origin in ("docker", "manual"):
        name = rest
    else:
        return None

    group = GROUP_NOT_RUNNING
    description = None
    if origin == "manual":
        state = UNKNOWN
    elif isinstance(snapshot.sockets, SourceError) or (
        origin == "docker" and isinstance(snapshot.docker, SourceError)
    ):
        state, group = UNKNOWN, GROUP_UNKNOWN
    elif unit is None:
        state = "not running"
    else:
        status = snapshot.unit_status(*unit)
        if isinstance(status, SourceError):
            errors.setdefault(status.source, status)
            state = UNKNOWN
        else:
            state = "running without a port" if status.state == "active" else status.state
            description = status.description

    return InventoryRow(
        identity_key=key,
        display_name=_annotated(note, "display_name") or description or name,
        description=_annotated(note, "description"),
        origin=origin,
        state=state,
        group=group,
        hidden=bool(note.hidden),  # rows built from annotations are never suppressed
        suppressed=False,
        access_paths=(),
        primary_port=note.primary_port,
        health_path=note.health_path,
        link_override=note.link_override,
    )


def _hidden(note: Any | None, suppressed: bool) -> bool:
    choice = _annotated(note, "hidden")
    return suppressed if choice is None else bool(choice)


def _annotated(note: Any | None, name: str) -> Any:
    return getattr(note, name) if note is not None else None

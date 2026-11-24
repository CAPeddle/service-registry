"""Listening TCP sockets, from ``ss -tlnpH``.

Run as root, ss names the processes on every socket; run as another user it
omits the ``users:(...)`` section for sockets that user does not own, so a
socket may carry no processes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from . import DEFAULT_TIMEOUT, SourceError, run_source

SOURCE = "sockets"
SS_ARGV = ("ss", "-tlnpH")

_PROCESS = re.compile(r'\("(?P<name>.*?)",pid=(?P<pid>\d+),')


@dataclass(frozen=True)
class SocketProcess:
    name: str
    pid: int


@dataclass(frozen=True)
class ListeningSocket:
    """One listening socket.

    ``address`` is the bind address without brackets: ``0.0.0.0``, ``::``,
    ``*``, ``127.0.0.1``, ``fd7a:...``. ``interface`` is set when the bind is
    scoped to a device, as in ``100.65.192.115%tailscale0``.
    """

    address: str
    port: int
    interface: str | None
    processes: tuple[SocketProcess, ...]

    @property
    def pids(self) -> tuple[int, ...]:
        return tuple(p.pid for p in self.processes)


def parse_ss(text: str) -> list[ListeningSocket]:
    """Parse ``ss -tlnpH`` output; lines that are not socket rows are skipped."""
    sockets = []
    for line in text.splitlines():
        # State, Recv-Q, Send-Q, local, peer, then the process section, which
        # may contain spaces inside process names.
        fields = line.split(None, 5)
        if len(fields) < 5:
            continue
        local = _parse_local(fields[3])
        if local is None:
            continue
        address, port, interface = local
        process_text = fields[5] if len(fields) > 5 else ""
        processes = tuple(
            SocketProcess(name=m["name"], pid=int(m["pid"]))
            for m in _PROCESS.finditer(process_text)
        )
        sockets.append(ListeningSocket(address, port, interface, processes))
    return sockets


def _parse_local(local: str) -> tuple[str, int, str | None] | None:
    host, sep, port = local.rpartition(":")
    if not sep or not port.isdigit():
        return None
    interface = None
    if "%" in host:
        host, interface = host.split("%", 1)
    return host.strip("[]"), int(port), interface


def list_sockets(
    *, argv: Sequence[str] = SS_ARGV, timeout: float = DEFAULT_TIMEOUT
) -> list[ListeningSocket] | SourceError:
    return run_source(SOURCE, argv, parse_ss, timeout)

"""Which systemd unit a process belongs to, from ``/proc/<pid>/cgroup``.

Expects the cgroup v2 line ``0::/path``. A process in a ``.service`` cgroup
under ``system.slice`` belongs to a system unit; one in a ``.service`` cgroup
under ``user@<uid>.service`` belongs to that user's unit. Everything else
(scopes such as tmux or login sessions, ``init.scope``, the user manager
itself) is unattributed.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

from . import SourceError, parse_source

SOURCE = "cgroups"

_USER_MANAGER = re.compile(r"user@(\d+)\.service")


@dataclass(frozen=True)
class UnitRef:
    scope: Literal["system", "user"]
    unit: str
    uid: int | None  # set for user units only


@dataclass(frozen=True)
class Unattributed:
    path: str


def parse_cgroup(text: str) -> UnitRef | Unattributed:
    path = ""
    for line in text.splitlines():
        if line.startswith("0::"):
            path = line[3:].strip()
            break

    segments = [s for s in path.split("/") if s]
    first = _first_below_slices(segments)
    if first is None:
        return Unattributed(path)
    index, name = first

    manager = _USER_MANAGER.fullmatch(name)
    if manager:
        inner = _first_below_slices(segments[index + 1:])
        if inner and inner[1].endswith(".service"):
            return UnitRef(scope="user", unit=inner[1], uid=int(manager.group(1)))
        return Unattributed(path)

    if name.endswith(".service") and segments[0] == "system.slice":
        return UnitRef(scope="system", unit=name, uid=None)
    return Unattributed(path)


def _first_below_slices(segments: list[str]) -> tuple[int, str] | None:
    """The first cgroup segment that is not a slice, with its index."""
    for index, segment in enumerate(segments):
        if not segment.endswith(".slice"):
            return index, segment
    return None


def read_cgroup(pid: int, *, proc_root: str = "/proc") -> UnitRef | Unattributed | SourceError:
    try:
        with open(os.path.join(proc_root, str(pid), "cgroup")) as handle:
            text = handle.read()
    except OSError as exc:
        return SourceError(SOURCE, f"cannot read cgroup of pid {pid}: {exc.strerror or exc}")
    return parse_source(SOURCE, parse_cgroup, text)

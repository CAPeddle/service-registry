"""Description and state of a systemd unit, from ``systemctl show``.

User units are read through the user's manager with ``--user -M <user>@``.
"""
from __future__ import annotations

import pwd
from dataclasses import dataclass

from . import DEFAULT_TIMEOUT, SourceError, run_source

SOURCE = "units"
_PROPERTIES = ("-p", "Description", "-p", "ActiveState", "-p", "LoadState")


@dataclass(frozen=True)
class UnitStatus:
    description: str
    active_state: str
    load_state: str

    @property
    def state(self) -> str:
        """``"not found"`` for a unit systemd does not know, else its ActiveState."""
        return "not found" if self.load_state == "not-found" else self.active_state


def parse_unit_show(text: str) -> UnitStatus:
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key] = value
    return UnitStatus(
        description=values.get("Description", ""),
        active_state=values.get("ActiveState", ""),
        load_state=values.get("LoadState", ""),
    )


def show_unit(
    unit: str,
    uid: int | None = None,
    *,
    systemctl: str = "systemctl",
    timeout: float = DEFAULT_TIMEOUT,
) -> UnitStatus | SourceError:
    """Status of a system unit, or of a user unit when ``uid`` is given."""
    if uid is None:
        argv = (systemctl, "show")
    else:
        try:
            user = pwd.getpwuid(uid).pw_name
        except KeyError:
            return SourceError(SOURCE, f"no user with uid {uid}")
        argv = (systemctl, "--user", "-M", f"{user}@", "show")
    return run_source(SOURCE, argv + _PROPERTIES + ("--", unit), parse_unit_show, timeout)

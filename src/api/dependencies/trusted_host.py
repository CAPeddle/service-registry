"""Accept write requests only when their Host (and Origin, if sent) is one of this server's names.

nginx passes every Host on port 80 to the app and there is no login, so a web
page could rebind its own domain name to this server's address and send
same-origin writes. The browser then sends that page's domain as Host and
Origin. Writes are accepted only for names an outside site cannot own: IP
literals, single-label names, ``.local`` names, the tailnet MagicDNS name and
the names in the ``trusted_hosts`` setting. Reads are not restricted.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Optional
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status

from src.api.dependencies.services import get_inventory_service
from src.config import settings
from src.services.discovery.inventory import InventoryService

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_HOST_AND_PORT = re.compile(r"(\[[^\]]*\]|[^:\[\]]*)(?::\d+)?")
_NAME = re.compile(r"[a-z0-9_-]+(?:\.[a-z0-9_-]+)*")


def parse_host(value: str) -> Optional[str]:
    """The lower-cased host of a ``host[:port]`` value, or None if it is malformed.

    Bracketed IPv6 literals keep their brackets.
    """
    match = _HOST_AND_PORT.fullmatch(value.lower())
    if match is None:
        return None
    host = match.group(1)
    if host.startswith("["):
        try:
            ipaddress.IPv6Address(host[1:-1])
        except ValueError:
            return None
        return host
    return host if _NAME.fullmatch(host) else None


def _trusted_by_name(host: str) -> bool:
    if host.startswith("[") or "." not in host or host.endswith(".local"):
        return True  # IPv6 literal, single label, mDNS
    try:
        ipaddress.IPv4Address(host)
        return True
    except ValueError:
        pass
    configured = {name.strip().lower() for name in settings.trusted_hosts.split(",")}
    return host in configured - {""}


def _origin_host(origin: str) -> str:
    try:
        return urlsplit(origin).netloc
    except ValueError:
        return ""


def require_trusted_host(
    request: Request, inventory: InventoryService = Depends(get_inventory_service)
) -> None:
    """Reject a write request from an untrusted Host or Origin with 403."""
    if request.method not in WRITE_METHODS:
        return
    values = [request.headers.get("host", "")]
    if "origin" in request.headers:
        values.append(_origin_host(request.headers["origin"]))
    hosts = [parse_host(value) for value in values]
    if None in hosts:
        _forbid()
    untrusted = {host for host in hosts if not _trusted_by_name(host)}
    # Discovery runs only for names the rules above do not settle.
    if untrusted and not untrusted <= inventory.get().tailnet_hosts:
        _forbid()


def _forbid() -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Changes are only accepted through this server's own addresses",
    )

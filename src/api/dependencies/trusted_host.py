"""Accept write requests only from this server's own pages, addressed by one of its names.

nginx passes every Host on port 80 to the app and there is no login, so a web
page could rebind its own domain name to this server's address and send
same-origin writes. The browser then sends that page's domain as Host and
Origin. Writes are accepted only for a Host an outside site cannot own: IP
literals, single-label names, ``.local`` names, the tailnet MagicDNS name and
the names in the ``trusted_hosts`` setting.

A page on another site can still send writes to one of those names. To refuse
them, an Origin must name the request's own Host, a ``Sec-Fetch-Site`` must
say ``same-origin`` or ``none``, and a request body must be declared
``application/json``, which a cross-site form or a no-preflight fetch cannot
send. Reads are not restricted.
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
BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
ALLOWED_FETCH_SITES = frozenset({"same-origin", "none"})  # "none": typed or bookmarked by the user

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


def _has_body(request: Request) -> bool:
    if "transfer-encoding" in request.headers:
        return True
    length = request.headers.get("content-length", "0")
    return not length.isdigit() or int(length) > 0


def _declared_json(request: Request) -> bool:
    media_type = request.headers.get("content-type", "").split(";", 1)[0]
    return media_type.strip().lower() == "application/json"


def require_trusted_host(
    request: Request, inventory: InventoryService = Depends(get_inventory_service)
) -> None:
    """Reject a write request from an untrusted Host or another origin with 403.

    A write body not declared ``application/json`` gets 415.
    """
    if request.method not in WRITE_METHODS:
        return
    headers = request.headers
    host = parse_host(headers.get("host", ""))
    if host is None:
        _forbid()
    if "origin" in headers and parse_host(_origin_host(headers["origin"])) != host:
        _forbid()
    if headers.get("sec-fetch-site", "same-origin").lower() not in ALLOWED_FETCH_SITES:
        _forbid()
    # Discovery runs only for names the rules above do not settle.
    if not _trusted_by_name(host) and host not in inventory.get().tailnet_hosts:
        _forbid()
    if request.method in BODY_METHODS and _has_body(request) and not _declared_json(request):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Send the request body as application/json",
        )


def _forbid() -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Changes are only accepted through this server's own addresses",
    )

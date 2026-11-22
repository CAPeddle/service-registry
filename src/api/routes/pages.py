"""HTML page routes: the landing page with the live inventory."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.api.dependencies.services import get_health_check_service, get_inventory_service
from src.models.base import get_db
from src.models.registration_attempt import PROTECTED_FIELDS
from src.repositories.annotation_repository import AnnotationRepository
from src.repositories.registration_attempt_repository import RegistrationAttemptRepository
from src.services.discovery.inventory import (
    GROUP_INTERNAL,
    GROUP_LAN,
    GROUP_NOT_RUNNING,
    GROUP_TAILNET,
    GROUP_UNKNOWN,
    INTERNAL,
    LAN,
    LAN_BLOCKED,
    TAILNET,
    AccessPath,
    Inventory,
    InventoryRow,
    InventoryService,
)
from src.services.health_check import (
    PROBE_HEADER,
    HealthCheckService,
    ProbeRequest,
    ProbeResult,
)

router = APIRouter()
templates = Jinja2Templates(directory="src/api/templates")

_HOSTNAME = re.compile(r"[a-zA-Z0-9.\-_]+")
_BRACKETED = re.compile(r"\[([0-9a-fA-F:.]+)\](?::\d+)?")

GROUP_HIDDEN = "hidden"
GROUP_TITLES = {
    GROUP_UNKNOWN: "Unknown",
    GROUP_LAN: "Web (LAN)",
    GROUP_TAILNET: "Tailnet",
    GROUP_INTERNAL: "Internal",
    GROUP_NOT_RUNNING: "Not running",
}

_FIELD_LABELS = {"description": "description", "health_path": "health path"}

_REACH_LABELS = {
    LAN: "LAN",
    LAN_BLOCKED: "blocked by firewall",
    TAILNET: "tailnet only",
    INTERNAL: "internal only",
}


def get_safe_hostname(request: Request) -> str:
    """Extract and sanitize the hostname from the Host header, without its port.

    Accepts plain hostnames and IPv4 addresses (letters, digits, dots,
    hyphens, underscores) and bracketed IPv6 literals such as ``[fd4e::1]``,
    which keep their brackets so they can go straight into a URL. Anything
    else, including CR/LF or other control characters, falls back to
    ``localhost``.
    """
    host_header = request.headers.get("host", "localhost")
    bracketed = _BRACKETED.fullmatch(host_header)
    if bracketed:
        try:
            ipaddress.IPv6Address(bracketed.group(1))
        except ValueError:
            return "localhost"
        return f"[{bracketed.group(1)}]"
    hostname = host_header.split(":")[0]
    if _HOSTNAME.fullmatch(hostname):  # fullmatch: "$" would let a trailing newline through
        return hostname
    return "localhost"


@dataclass
class PathView:
    text: str
    href: Optional[str]
    reach: str
    label: str


@dataclass
class RowView:
    row: InventoryRow
    href: Optional[str]
    paths: list[PathView]
    health: str


@dataclass
class GroupView:
    key: str
    title: str
    rows: list[RowView]
    others: list[RowView]


@dataclass
class HeldFieldView:
    label: str
    posted: Optional[str]
    current: Optional[str]


@dataclass
class HeldView:
    attempt_id: int
    service: str
    identity_key: str
    received: str
    fields: list[HeldFieldView]


@router.get("/")
async def index(
    request: Request,
    refresh: bool = False,
    show_hidden: bool = False,
    inventory_service: InventoryService = Depends(get_inventory_service),
    prober: HealthCheckService = Depends(get_health_check_service),
    db: Session = Depends(get_db),
) -> Response:
    """Landing page: what runs on this host and how to reach each service."""
    if PROBE_HEADER in request.headers:
        # This app probing its own port (or nginx in front of it): answer without probing again.
        return PlainTextResponse("ok")
    host = get_safe_hostname(request)
    inventory = await run_in_threadpool(inventory_service.get, refresh=refresh)
    held = await run_in_threadpool(_held_views, db, inventory)

    shown = [row for row in inventory.rows if show_hidden or not row.hidden]
    requests = {row.identity_key: _probe_requests(row) for row in shown}
    batch = [r for rs in requests.values() for r in rs]
    results = await prober.probe_batch(batch) if batch else {}

    views = [_row_view(row, requests[row.identity_key], results, host) for row in shown]
    groups = [
        GroupView(key, title, [v for v in views if not v.row.hidden and v.row.group == key], [])
        for key, title in GROUP_TITLES.items()
    ]
    groups = [g for g in groups if g.key != GROUP_UNKNOWN or g.rows]
    hidden = [v for v in views if v.row.hidden]
    if show_hidden:
        groups.append(
            GroupView(
                GROUP_HIDDEN,
                "Hidden",
                [v for v in hidden if v.row.origin != "other"],
                [v for v in hidden if v.row.origin == "other"],
            )
        )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "held": held,
            "groups": groups,
            "errors": inventory.errors,
            "show_hidden": show_hidden,
            "hidden_count": sum(1 for row in inventory.rows if row.hidden),
        },
    )


def _held_views(db: Session, inventory: Inventory) -> list[HeldView]:
    """Held registrations, with the posted and the current value of each held field."""
    annotations = AnnotationRepository(db)
    views = []
    for attempt in RegistrationAttemptRepository(db).list():
        note = annotations.get(attempt.identity_key)
        row = inventory.row(attempt.identity_key)
        name = row.display_name if row else getattr(note, "display_name", None)
        fields = [
            HeldFieldView(
                _FIELD_LABELS[field],
                getattr(attempt, PROTECTED_FIELDS[field]),
                getattr(note, field, None),
            )
            for field in attempt.held_fields
        ]
        views.append(
            HeldView(
                attempt_id=attempt.id,
                service=name or attempt.identity_key,
                identity_key=attempt.identity_key,
                received=f"{attempt.received_at:%Y-%m-%d %H:%M} UTC",
                fields=fields,
            )
        )
    return views


def _probe_requests(row: InventoryRow) -> list[ProbeRequest]:
    """One probe per local port; the primary port also checks the annotated health path."""
    ports = sorted({path.port for path in row.access_paths})
    return [
        ProbeRequest(port, row.health_path if port == row.primary_port else None) for port in ports
    ]


def _row_view(
    row: InventoryRow,
    requests: list[ProbeRequest],
    results: dict[ProbeRequest, ProbeResult],
    host: str,
) -> RowView:
    by_port = {req.port: results.get(req) for req in requests}
    ordered = sorted(row.access_paths, key=lambda p: (not p.is_primary, p.port))
    paths = [_path_view(path, by_port.get(path.port), host) for path in ordered]
    href = row.link_override or next((p.href for p in paths if p.href), None)
    primary = next((req for req in requests if req.port == row.primary_port), None)
    health = _health(row, results.get(primary) if primary else None)
    return RowView(row=row, href=href, paths=paths, health=health)


def _path_view(path: AccessPath, result: Optional[ProbeResult], host: str) -> PathView:
    link = path.link(host)
    answered_http = result is not None and result.is_http is True
    if path.reach == INTERNAL:
        text = f"127.0.0.1:{path.port}"
    elif path.url:
        text = urlsplit(path.url).netloc
    elif path.reach == TAILNET:
        text = f"port {path.port}"
    else:
        text = f"{host}:{path.port}"
    return PathView(
        text=text,
        href=link if link and answered_http else None,
        reach=path.reach,
        label=_REACH_LABELS.get(path.reach, "reachability unknown"),
    )


def _health(row: InventoryRow, result: Optional[ProbeResult]) -> str:
    if not row.health_path or not row.access_paths:
        return "not checked"
    if result is None or result.health is None:
        return "checking failed"
    return "healthy" if result.health.is_healthy else "unhealthy"

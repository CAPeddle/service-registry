"""Tailscale serve mappings, from ``tailscale serve status --json``.

Each ``Web`` entry ``<fqdn>:<port>`` whose ``/`` handler proxies to a local
port becomes a mapping from the tailnet URL to that local target. tailscaled
itself listens on the front port, so callers can fold those listeners into the
backend's row. TCP forwarding and Funnel settings are not read.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence
from urllib.parse import urlsplit

from . import DEFAULT_TIMEOUT, SourceError, run_source

SOURCE = "tailscale"
SERVE_ARGV = ("tailscale", "serve", "status", "--json")


@dataclass(frozen=True)
class ServeMapping:
    front_port: int  # the port tailscaled listens on
    url: str  # e.g. "https://z2.example.ts.net/" or "http://z2.example.ts.net:8765/"
    target_host: str  # as written in the proxy, "127.0.0.1" for a bare port
    target_port: int


def parse_serve_status(text: str) -> list[ServeMapping]:
    status = json.loads(text) or {}
    tcp = status.get("TCP") or {}
    mappings = []
    for host_port, web in (status.get("Web") or {}).items():
        fqdn, _, port_text = host_port.rpartition(":")
        if not port_text.isdigit():
            continue
        front_port = int(port_text)
        handler = ((web or {}).get("Handlers") or {}).get("/") or {}
        target = parse_proxy_target(handler.get("Proxy", ""))
        url = _tailnet_url(fqdn, front_port, tcp.get(port_text) or {})
        if target is None or url is None:
            continue
        mappings.append(ServeMapping(front_port, url, target[0], target[1]))
    return mappings


def parse_proxy_target(proxy: str) -> tuple[str, int] | None:
    """Local (host, port) a serve handler proxies to, or None if unrecognised.

    Accepts ``http://127.0.0.1:N``, ``https+insecure://127.0.0.1:N``,
    ``localhost:N`` and a bare ``N`` (which tailscale serves from 127.0.0.1).
    """
    proxy = proxy.strip()
    if proxy.isdigit():
        return "127.0.0.1", int(proxy)
    if "://" in proxy:
        parts = urlsplit(proxy)
        try:
            port = parts.port
        except ValueError:
            return None
        if parts.hostname and port:
            return parts.hostname, port
        return None
    host, sep, port_text = proxy.rpartition(":")
    if sep and host and port_text.isdigit():
        return host.strip("[]"), int(port_text)
    return None


def _tailnet_url(fqdn: str, port: int, tcp_entry: dict) -> str | None:
    if tcp_entry.get("HTTPS"):
        scheme, default_port = "https", 443
    elif tcp_entry.get("HTTP"):
        scheme, default_port = "http", 80
    else:
        return None
    suffix = "" if port == default_port else f":{port}"
    return f"{scheme}://{fqdn}{suffix}/"


def list_serve_mappings(
    *, argv: Sequence[str] = SERVE_ARGV, timeout: float = DEFAULT_TIMEOUT
) -> list[ServeMapping] | SourceError:
    return run_source(SOURCE, argv, parse_serve_status, timeout)

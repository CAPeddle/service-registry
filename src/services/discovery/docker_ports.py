"""Docker published ports, from ``docker ps --format '{{json .}}'``.

Maps each published host (bind address, port) to the container behind it, so
docker-proxy listeners can be named after their compose project and service.
Bind addresses use the same forms as the sockets source (``::`` without
brackets).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Sequence

from . import DEFAULT_TIMEOUT, SourceError, run_source

SOURCE = "docker"
DOCKER_ARGV = ("docker", "ps", "--no-trunc", "--format", "{{json .}}")

_PROJECT_LABEL = "com.docker.compose.project"
_SERVICE_LABEL = "com.docker.compose.service"

# "127.0.0.1:3000->3000/tcp", ":::8080->80/tcp", "[::]:8080->80/tcp",
# "0.0.0.0:8000-8001->8000-8001/tcp"
_PUBLISHED = re.compile(r"^(?P<host>.*):(?P<first>\d+)(?:-(?P<last>\d+))?->[\d-]+/(?P<proto>\w+)$")


@dataclass(frozen=True)
class Container:
    name: str
    project: str | None
    service: str | None


def parse_docker_ps(text: str) -> dict[tuple[str, int], Container]:
    published: dict[tuple[str, int], Container] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        labels = _parse_labels(row.get("Labels", ""))
        container = Container(
            name=row.get("Names", "").split(",")[0],
            project=labels.get(_PROJECT_LABEL),
            service=labels.get(_SERVICE_LABEL),
        )
        for entry in row.get("Ports", "").split(","):
            match = _PUBLISHED.match(entry.strip())
            if not match or match["proto"] != "tcp":
                continue
            host = match["host"].strip("[]")
            first = int(match["first"])
            last = int(match["last"] or first)
            for port in range(first, last + 1):
                published[(host, port)] = container
    return published


def _parse_labels(labels: str) -> dict[str, str]:
    """Pick the compose labels out of docker's comma-joined ``key=value`` list.

    Other label values may themselves contain commas, so only pairs whose key
    is exactly one of the compose keys are kept.
    """
    found = {}
    for pair in labels.split(","):
        key, sep, value = pair.partition("=")
        if sep and key in (_PROJECT_LABEL, _SERVICE_LABEL):
            found[key] = value
    return found


def list_published_ports(
    *, argv: Sequence[str] = DOCKER_ARGV, timeout: float = DEFAULT_TIMEOUT
) -> dict[tuple[str, int], Container] | SourceError:
    return run_source(SOURCE, argv, parse_docker_ps, timeout)

"""Live discovery sources.

Each source module pairs a pure parser (raw text in, typed records out) with a
runner that executes a fixed argument list without a shell, under a timeout,
and returns either the parsed records or a ``SourceError`` naming the source.
Runners never raise, so one failing source cannot take down the page.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence, TypeVar

DEFAULT_TIMEOUT = 2.0

T = TypeVar("T")


@dataclass(frozen=True)
class SourceError:
    """A discovery source that could not produce data."""

    source: str
    message: str


def run_source(
    source: str,
    argv: Sequence[str],
    parse: Callable[[str], T],
    timeout: float = DEFAULT_TIMEOUT,
) -> T | SourceError:
    """Run ``argv`` and parse its stdout, turning every failure into a SourceError."""
    try:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            # Parsers match English output (ufw translates its status lines).
            env={**os.environ, "LC_ALL": "C"},
        )
    except FileNotFoundError:
        return SourceError(source, f"command not found: {argv[0]}")
    except subprocess.TimeoutExpired:
        return SourceError(source, f"{argv[0]} timed out after {timeout:g}s")
    except OSError as exc:
        return SourceError(source, f"could not run {argv[0]}: {exc}")

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        reason = detail[0] if detail else "no output"
        return SourceError(source, f"{argv[0]} exited {completed.returncode}: {reason}")

    return parse_source(source, parse, completed.stdout)


def parse_source(source: str, parse: Callable[[str], T], text: str) -> T | SourceError:
    """Apply ``parse`` to ``text``, reporting a parser failure as a SourceError."""
    try:
        return parse(text)
    except Exception as exc:
        return SourceError(source, f"unreadable output: {exc}")

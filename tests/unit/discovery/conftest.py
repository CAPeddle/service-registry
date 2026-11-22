"""Shared helpers for discovery source tests."""
import stat
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "z2"


@pytest.fixture
def fixture_text():
    """Read a captured Z2 output by file name."""

    def read(name: str) -> str:
        return (FIXTURES / name).read_text()

    return read


@pytest.fixture
def slow_command(tmp_path):
    """An executable that ignores its arguments and sleeps for 5 seconds."""
    script = tmp_path / "slow"
    script.write_text("#!/bin/sh\nexec sleep 5\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)

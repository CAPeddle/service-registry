"""Tests for the systemd unit status source."""
import os
import pwd

from src.services.discovery import SourceError
from src.services.discovery import units
from src.services.discovery.units import SOURCE, UnitStatus, parse_unit_show, show_unit

ACTIVE = "Description=Finance Tracker\nActiveState=active\nLoadState=loaded\n"
MISSING = "Description=nope.service\nActiveState=inactive\nLoadState=not-found\n"


def test_parses_loaded_active_unit():
    status = parse_unit_show(ACTIVE)
    assert status == UnitStatus(
        description="Finance Tracker", active_state="active", load_state="loaded"
    )
    assert status.state == "active"


def test_not_found_unit():
    assert parse_unit_show(MISSING).state == "not found"


def test_failed_unit():
    text = "Description=X\nActiveState=failed\nLoadState=loaded\n"
    assert parse_unit_show(text).state == "failed"


def test_value_containing_equals_sign_is_kept_whole():
    text = "Description=a=b tool\nActiveState=active\nLoadState=loaded\n"
    assert parse_unit_show(text).description == "a=b tool"


def _capture_argv(monkeypatch):
    calls = []

    def fake_run_source(source, argv, parse, timeout):
        calls.append(argv)
        return parse(ACTIVE)

    monkeypatch.setattr(units, "run_source", fake_run_source)
    return calls


def test_system_unit_argv(monkeypatch):
    calls = _capture_argv(monkeypatch)
    assert show_unit("finance-tracker.service").state == "active"
    assert calls == [(
        "systemctl", "show",
        "-p", "Description", "-p", "ActiveState", "-p", "LoadState",
        "--", "finance-tracker.service",
    )]


def test_user_unit_argv_resolves_user_name(monkeypatch):
    calls = _capture_argv(monkeypatch)
    uid = os.getuid()
    name = pwd.getpwuid(uid).pw_name
    show_unit("groceries-web.service", uid=uid)
    assert calls == [(
        "systemctl", "--user", "-M", f"{name}@", "show",
        "-p", "Description", "-p", "ActiveState", "-p", "LoadState",
        "--", "groceries-web.service",
    )]


def test_unknown_uid_is_an_error():
    result = show_unit("x.service", uid=2_000_000_000)
    assert isinstance(result, SourceError)
    assert result.source == SOURCE


def test_runner_errors_name_the_source(slow_command):
    for result in (
        show_unit("x.service", systemctl="/nonexistent/systemctl"),
        show_unit("x.service", systemctl="false"),
        show_unit("x.service", systemctl=slow_command, timeout=0.2),
    ):
        assert isinstance(result, SourceError)
        assert result.source == SOURCE

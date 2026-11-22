"""Tests for the shared command runner used by every discovery source."""
import time

from src.services.discovery import SourceError, run_source


def _parse_upper(text: str) -> str:
    return text.strip().upper()


def _parse_fails(text: str) -> str:
    raise ValueError("no Status line")


def test_returns_parsed_output():
    assert run_source("demo", ("echo", "hello"), _parse_upper) == "HELLO"


def test_missing_command_returns_error_naming_source():
    result = run_source("demo", ("/nonexistent/demo-binary",), _parse_upper)
    assert isinstance(result, SourceError)
    assert result.source == "demo"
    assert "not found" in result.message


def test_non_zero_exit_returns_error_with_stderr():
    result = run_source("demo", ("sh", "-c", "echo 'need root' >&2; exit 1"), _parse_upper)
    assert isinstance(result, SourceError)
    assert result.source == "demo"
    assert "need root" in result.message


def test_timeout_returns_error_without_waiting_for_command(slow_command):
    started = time.monotonic()
    result = run_source("demo", (slow_command,), _parse_upper, timeout=0.2)
    assert time.monotonic() - started < 2
    assert isinstance(result, SourceError)
    assert "timed out" in result.message


def test_parser_failure_returns_error_not_exception():
    result = run_source("demo", ("echo", "garbage"), _parse_fails)
    assert isinstance(result, SourceError)
    assert result.source == "demo"
    assert "no Status line" in result.message


def test_command_sees_a_closed_stdin():
    # A command that waits for input must not hang the request.
    assert run_source("demo", ("cat",), _parse_upper, timeout=1) == ""

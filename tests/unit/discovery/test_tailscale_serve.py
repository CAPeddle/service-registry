"""Tests for the Tailscale serve source."""
import json

import pytest

from src.services.discovery import SourceError
from src.services.discovery.tailscale_serve import (
    SOURCE,
    ServeMapping,
    list_serve_mappings,
    parse_proxy_target,
    parse_serve_status,
)


def test_fixture_maps_tailnet_urls_to_local_targets(fixture_text):
    mappings = parse_serve_status(fixture_text("tailscale-serve.json"))
    assert sorted(mappings, key=lambda m: m.front_port) == [
        ServeMapping(front_port=443, url="https://z2.example-tailnet.ts.net/",
                     target_host="127.0.0.1", target_port=8790),
        ServeMapping(front_port=8443, url="https://z2.example-tailnet.ts.net:8443/",
                     target_host="127.0.0.1", target_port=3000),
        ServeMapping(front_port=8765, url="http://z2.example-tailnet.ts.net:8765/",
                     target_host="0.0.0.0", target_port=8766),
    ]


@pytest.mark.parametrize("proxy, expected", [
    ("http://127.0.0.1:8790", ("127.0.0.1", 8790)),
    ("http://0.0.0.0:8766", ("0.0.0.0", 8766)),
    ("3000", ("127.0.0.1", 3000)),
    ("localhost:3000", ("localhost", 3000)),
    ("https+insecure://127.0.0.1:9443", ("127.0.0.1", 9443)),
])
def test_proxy_forms(proxy, expected):
    assert parse_proxy_target(proxy) == expected


def _serve(handlers, tcp=None):
    return json.dumps({
        "TCP": tcp or {"443": {"HTTPS": True}},
        "Web": {"z2.example-tailnet.ts.net:443": {"Handlers": handlers}},
    })


def test_only_root_handler_is_recorded():
    status = _serve({"/api": {"Proxy": "http://127.0.0.1:9001"}, "/": {"Proxy": "9000"}})
    assert [m.target_port for m in parse_serve_status(status)] == [9000]


def test_non_root_handler_alone_records_nothing():
    assert parse_serve_status(_serve({"/api": {"Proxy": "9001"}})) == []


def test_handler_without_proxy_records_nothing():
    assert parse_serve_status(_serve({"/": {"Path": "/srv/www"}})) == []


def test_http_on_port_80_omits_the_port():
    status = json.dumps({
        "TCP": {"80": {"HTTP": True}},
        "Web": {"z2.example-tailnet.ts.net:80": {"Handlers": {"/": {"Proxy": "9000"}}}},
    })
    [mapping] = parse_serve_status(status)
    assert mapping.url == "http://z2.example-tailnet.ts.net/"


def test_front_port_without_tcp_scheme_records_nothing():
    assert parse_serve_status(_serve({"/": {"Proxy": "9000"}}, tcp={"443": {}})) == []


def test_empty_serve_config_yields_no_mappings():
    assert parse_serve_status("{}") == []


def test_runner_parses_command_output(fixture_text, tmp_path):
    path = tmp_path / "serve.json"
    path.write_text(fixture_text("tailscale-serve.json"))
    result = list_serve_mappings(argv=("cat", str(path)))
    assert {m.target_port for m in result} == {8790, 3000, 8766}


def test_runner_error_on_unparseable_output():
    result = list_serve_mappings(argv=("echo", "not json"))
    assert isinstance(result, SourceError)
    assert result.source == SOURCE


def test_runner_errors_name_the_source(slow_command):
    for result in (
        list_serve_mappings(argv=("/nonexistent/tailscale",)),
        list_serve_mappings(argv=("false",)),
        list_serve_mappings(argv=(slow_command,), timeout=0.2),
    ):
        assert isinstance(result, SourceError)
        assert result.source == SOURCE

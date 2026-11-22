"""Tests for the Docker published-port source."""
import json

from src.services.discovery import SourceError
from src.services.discovery.docker_ports import (
    SOURCE,
    Container,
    list_published_ports,
    parse_docker_ps,
)


def test_fixture_maps_published_ports_to_compose_identity(fixture_text):
    assert parse_docker_ps(fixture_text("docker-ps.jsonl")) == {
        ("127.0.0.1", 3000): Container(name="app-app-1", project="app", service="app"),
        ("127.0.0.1", 8790): Container(name="awcp-awcp-1", project="awcp", service="awcp"),
    }


def test_unpublished_port_yields_nothing():
    line = json.dumps({"Names": "awcp-db-1", "Labels": "", "Ports": "5432/tcp"})
    assert parse_docker_ps(line) == {}


def test_compose_labels_matched_by_exact_key_among_lookalikes():
    labels = ",".join([
        "com.docker.compose.project.config_files=/srv/demo/compose.yaml",
        "com.docker.compose.project.working_dir=/srv/demo",
        "com.docker.compose.project=demo",
        "com.docker.compose.service=web",
        "com.docker.compose.depends_on=",
    ])
    line = json.dumps({"Names": "demo-web-1", "Labels": labels, "Ports": "127.0.0.1:9000->80/tcp"})
    assert parse_docker_ps(line) == {
        ("127.0.0.1", 9000): Container(name="demo-web-1", project="demo", service="web"),
    }


def test_container_without_compose_labels_keeps_its_name():
    line = json.dumps({"Names": "standalone", "Labels": "", "Ports": "0.0.0.0:8081->80/tcp"})
    assert parse_docker_ps(line) == {
        ("0.0.0.0", 8081): Container(name="standalone", project=None, service=None),
    }


def test_dual_stack_publish_uses_socket_address_forms():
    line = json.dumps({
        "Names": "web",
        "Labels": "",
        "Ports": "0.0.0.0:8082->80/tcp, :::8082->80/tcp, [::]:8083->81/tcp, 0.0.0.0:5353->53/udp",
    })
    assert set(parse_docker_ps(line)) == {("0.0.0.0", 8082), ("::", 8082), ("::", 8083)}


def test_published_port_range_maps_every_port():
    line = json.dumps({"Names": "r", "Labels": "", "Ports": "127.0.0.1:7000-7002->7000-7002/tcp"})
    assert set(parse_docker_ps(line)) == {("127.0.0.1", 7000), ("127.0.0.1", 7001), ("127.0.0.1", 7002)}


def test_empty_output_yields_no_ports():
    assert parse_docker_ps("") == {}


def test_runner_parses_command_output(fixture_text, tmp_path):
    path = tmp_path / "docker.jsonl"
    path.write_text(fixture_text("docker-ps.jsonl"))
    result = list_published_ports(argv=("cat", str(path)))
    assert ("127.0.0.1", 3000) in result


def test_runner_error_on_unparseable_output():
    result = list_published_ports(argv=("echo", "Cannot connect to the Docker daemon"))
    assert isinstance(result, SourceError)
    assert result.source == SOURCE


def test_runner_errors_name_the_source(slow_command):
    for result in (
        list_published_ports(argv=("/nonexistent/docker",)),
        list_published_ports(argv=("false",)),
        list_published_ports(argv=(slow_command,), timeout=0.2),
    ):
        assert isinstance(result, SourceError)
        assert result.source == SOURCE

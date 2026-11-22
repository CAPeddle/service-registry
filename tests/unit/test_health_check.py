"""Tests for health check service."""
import socket
import threading
import time
from collections import Counter

import httpx
import pytest

from src.api.dependencies.services import get_health_check_service
from src.services.health_check import HealthCheckService, ProbeRequest


# --- Concurrent probes against real local servers -------------------------


class LocalServer:
    """Tiny threaded TCP server on 127.0.0.1 with a per-connection behavior."""

    def __init__(self, behavior):
        self.behavior = behavior
        self.requests = Counter()
        self.release = threading.Event()
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(64)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            data = conn.recv(4096)
            parts = data.split(b" ", 2)
            path = parts[1].decode() if len(parts) > 1 else ""
            self.requests[path] += 1
            self.behavior(self, conn, path)
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self.release.set()
        self._sock.close()


def _http(status: int) -> bytes:
    return (f"HTTP/1.1 {status} X\r\nContent-Length: 0\r\n" f"Connection: close\r\n\r\n").encode()


def _routes(server, conn, path):
    if path == "/":
        conn.sendall(_http(404))
    elif path == "/ok":
        conn.sendall(_http(200))
    else:
        conn.sendall(_http(500))


def _reset(server, conn, path):
    # Abortive close sends RST instead of FIN
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")


def _garbage(server, conn, path):
    conn.sendall(b"SSH-2.0-not-http\r\n")


def _hang(server, conn, path):
    server.release.wait(10)


def _no_content(server, conn, path):
    conn.sendall(_http(204))


def _root_answers_health_hangs(server, conn, path):
    if path == "/":
        conn.sendall(_http(200))
    else:
        server.release.wait(10)


@pytest.fixture
def make_server():
    servers = []

    def factory(behavior):
        s = LocalServer(behavior)
        servers.append(s)
        return s

    yield factory
    for s in servers:
        s.close()


@pytest.fixture
def prober():
    return HealthCheckService()


async def test_port_answering_404_counts_as_http(make_server, prober):
    srv = make_server(_routes)
    req = ProbeRequest(srv.port)
    result = (await prober.probe_batch([req]))[req]
    assert result.is_http is True
    assert result.checking_failed is False


async def test_reset_and_non_http_ports_are_not_http(make_server, prober):
    reset = make_server(_reset)
    garbage = make_server(_garbage)
    reqs = [ProbeRequest(reset.port), ProbeRequest(garbage.port)]
    results = await prober.probe_batch(reqs)
    assert results[reqs[0]].is_http is False
    assert results[reqs[1]].is_http is False
    assert results[reqs[0]].checking_failed is False


async def test_closed_port_is_not_http(prober):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    req = ProbeRequest(port)
    assert (await prober.probe_batch([req]))[req].is_http is False


async def test_health_200_is_healthy_and_500_is_unhealthy(make_server, prober):
    srv = make_server(_routes)
    ok = ProbeRequest(srv.port, "/ok")
    bad = ProbeRequest(srv.port, "/bad")
    none = ProbeRequest(srv.port)
    results = await prober.probe_batch([ok, bad, none])
    assert results[ok].health.is_healthy is True
    assert results[ok].health.status_code == 200
    assert results[bad].health.is_healthy is False
    assert results[bad].health.status_code == 500
    assert results[none].health is None
    assert srv.requests["/ok"] == 1 and srv.requests["/bad"] == 1


async def test_health_any_2xx_is_healthy(make_server, prober):
    srv = make_server(_no_content)
    req = ProbeRequest(srv.port, "/health")
    health = (await prober.probe_batch([req]))[req].health
    assert health.is_healthy is True
    assert health.status_code == 204


async def test_hanging_health_path_is_unhealthy_and_keeps_the_http_result(make_server):
    prober = HealthCheckService()
    srv = make_server(_root_answers_health_hangs)
    req = ProbeRequest(srv.port, "/health")
    start = time.monotonic()
    result = (await prober.probe_batch([req]))[req]
    assert time.monotonic() - start < 2.0
    assert result.checking_failed is False
    assert result.is_http is True
    assert result.health.is_healthy is False
    assert result.health.error == "Timeout"


async def test_health_path_without_leading_slash(make_server, prober):
    srv = make_server(_routes)
    req = ProbeRequest(srv.port, "ok")
    assert (await prober.probe_batch([req]))[req].health.is_healthy is True


async def test_hanging_probes_return_within_budget(make_server):
    prober = HealthCheckService()
    servers = [make_server(_hang) for _ in range(15)]
    reqs = [ProbeRequest(s.port, "/health") for s in servers]
    start = time.monotonic()
    results = await prober.probe_batch(reqs)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0
    assert len(results) == 15
    assert all(r.checking_failed for r in results.values())


async def test_hang_does_not_delay_responsive_probe(make_server, prober):
    hang = make_server(_hang)
    good = make_server(_routes)
    h, g = ProbeRequest(hang.port), ProbeRequest(good.port, "/ok")
    start = time.monotonic()
    results = await prober.probe_batch([h, g])
    assert time.monotonic() - start < 2.0
    assert results[h].checking_failed is True
    assert results[g].is_http is True and results[g].health.is_healthy is True


async def test_second_batch_inside_cache_window_does_not_reprobe(make_server, prober):
    srv = make_server(_routes)
    req = ProbeRequest(srv.port, "/ok")
    await prober.probe_batch([req])
    await prober.probe_batch([req])
    assert srv.requests["/"] == 1
    assert srv.requests["/ok"] == 1


async def test_http_cache_expires_before_health_cache(make_server):
    prober = HealthCheckService(http_cache_ttl=0, cache_ttl=60)
    srv = make_server(_routes)
    req = ProbeRequest(srv.port, "/ok")
    await prober.probe_batch([req])
    await prober.probe_batch([req])
    assert srv.requests["/"] == 2
    assert srv.requests["/ok"] == 1


def test_probe_url_is_always_loopback():
    for path in ["/health", "health", "//evil.example/x", "@evil.example", "/a/../b"]:
        url = HealthCheckService.build_probe_url(8080, path)
        assert httpx.URL(url).host == "127.0.0.1"
        assert httpx.URL(url).port == 8080
    assert HealthCheckService.build_probe_url(8080, None) == "http://127.0.0.1:8080/"


def test_probe_url_rejects_invalid_port():
    for bad in [0, 70000, -1]:
        with pytest.raises(ValueError):
            HealthCheckService.build_probe_url(bad, None)


def test_shared_provider_returns_same_instance():
    assert get_health_check_service() is get_health_check_service()

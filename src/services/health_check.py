"""Health check service for monitoring service health."""
import asyncio
import httpx
import time
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta, UTC

# Seconds a health request leaves of the batch budget, and the shortest it may take.
_BUDGET_MARGIN = 0.25
_MIN_HEALTH_TIMEOUT = 0.1

# Sent with every probe so this app's own landing page can answer without probing again.
PROBE_HEADER = "X-Service-Registry-Probe"


@dataclass
class HealthStatus:
    """Health check result."""

    is_healthy: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    checked_at: datetime = None

    def __post_init__(self):
        if self.checked_at is None:
            self.checked_at = datetime.now(UTC)


@dataclass(frozen=True)
class ProbeRequest:
    """One port to probe, with an optional health path to check."""

    port: int
    health_path: Optional[str] = None


@dataclass
class ProbeResult:
    """Outcome of probing one port.

    is_http is None and checking_failed is True when the probe did not
    finish in time. health is None when no health path was requested.
    """

    is_http: Optional[bool] = None
    health: Optional[HealthStatus] = None
    checking_failed: bool = False


class HealthCheckService:
    """Service for checking health of registered services."""

    def __init__(
        self,
        timeout: float = 2.0,
        cache_ttl: int = 60,
        http_timeout: float = 0.5,
        http_cache_ttl: float = 10.0,
        budget: float = 1.5,
    ):
        """Initialize health check service.

        Args:
            timeout: Request timeout in seconds for health checks, capped to fit the budget
            cache_ttl: Health result cache time-to-live in seconds
            http_timeout: How long a port has to answer GET / to count as HTTP
            http_cache_ttl: Cache time-to-live for "is HTTP" results in seconds
            budget: Total seconds one probe_batch call may take
        """
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.http_timeout = http_timeout
        self.http_cache_ttl = http_cache_ttl
        self.budget = budget
        self._cache: dict[str, HealthStatus] = {}
        self._http_cache: dict[int, tuple[float, bool]] = {}

    @staticmethod
    def build_probe_url(port: int, path: Optional[str]) -> str:
        """Build a loopback URL for a port; the host is never configurable."""
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"Invalid port: {port!r}")
        path = path or "/"
        if not path.startswith("/"):
            path = f"/{path}"
        return f"http://127.0.0.1:{port}{path}"

    async def probe_batch(self, requests: list[ProbeRequest]) -> dict[ProbeRequest, ProbeResult]:
        """Probe all requests concurrently within one shared time budget.

        Probes still running when the budget ends are cancelled and reported
        with checking_failed=True.
        """
        unique = list(dict.fromkeys(requests))
        results: dict[ProbeRequest, ProbeResult] = {}
        async with httpx.AsyncClient(follow_redirects=False, headers={PROBE_HEADER: "1"}) as client:
            tasks = {asyncio.ensure_future(self._probe_one(client, req)): req for req in unique}
            done, pending = await asyncio.wait(tasks, timeout=self.budget)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        for task, req in tasks.items():
            if task in done and not task.cancelled() and task.exception() is None:
                results[req] = task.result()
            else:
                results[req] = ProbeResult(checking_failed=True)
        return results

    async def _probe_one(self, client: httpx.AsyncClient, req: ProbeRequest) -> ProbeResult:
        is_http, health = await asyncio.gather(
            self._probe_http(client, req.port),
            self._probe_health(client, req),
        )
        if is_http is None:
            return ProbeResult(health=health, checking_failed=True)
        return ProbeResult(is_http=is_http, health=health)

    async def _probe_http(self, client: httpx.AsyncClient, port: int) -> Optional[bool]:
        cached = self._http_cache.get(port)
        if cached and time.monotonic() - cached[0] < self.http_cache_ttl:
            return cached[1]
        url = self.build_probe_url(port, None)
        try:
            await client.get(url, timeout=self.http_timeout)
            is_http = True
        except httpx.TimeoutException:
            return None
        except httpx.HTTPError:
            is_http = False
        self._http_cache[port] = (time.monotonic(), is_http)
        return is_http

    async def _probe_health(
        self, client: httpx.AsyncClient, req: ProbeRequest
    ) -> Optional[HealthStatus]:
        if not req.health_path:
            return None
        url = self.build_probe_url(req.port, req.health_path)
        cached = self._cache.get(url)
        if cached and datetime.now(UTC) - cached.checked_at < timedelta(seconds=self.cache_ttl):
            return cached
        # Stay inside the batch budget so a hang is recorded as a timeout, not cancelled.
        timeout = max(_MIN_HEALTH_TIMEOUT, min(self.timeout, self.budget - _BUDGET_MARGIN))
        try:
            response = await client.get(url, timeout=timeout)
            status = HealthStatus(
                is_healthy=200 <= response.status_code < 300,
                status_code=response.status_code,
            )
        except httpx.TimeoutException:
            status = HealthStatus(is_healthy=False, error="Timeout")
        except Exception as e:
            status = HealthStatus(is_healthy=False, error=f"Error: {e}")
        self._cache[url] = status
        return status


shared_health_check_service = HealthCheckService()

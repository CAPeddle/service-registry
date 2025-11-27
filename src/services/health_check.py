"""Health check service for monitoring service health."""
import httpx
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta, UTC


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


class HealthCheckService:
    """Service for checking health of registered services."""

    def __init__(self, timeout: float = 2.0, cache_ttl: int = 60):
        """Initialize health check service.

        Args:
            timeout: Request timeout in seconds
            cache_ttl: Cache time-to-live in seconds
        """
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: dict[str, HealthStatus] = {}

    def check_health(self, url: str, use_cache: bool = True) -> HealthStatus:
        """Check health of a service endpoint.

        Args:
            url: Full URL to health endpoint
            use_cache: Whether to use cached result if available

        Returns:
            HealthStatus object with results
        """
        # Check cache
        if use_cache and url in self._cache:
            cached = self._cache[url]
            if datetime.now(UTC) - cached.checked_at < timedelta(seconds=self.cache_ttl):
                return cached

        # Perform health check
        try:
            response = httpx.get(url, timeout=self.timeout)
            status = HealthStatus(
                is_healthy=response.status_code == 200,
                status_code=response.status_code
            )
        except httpx.TimeoutException:
            status = HealthStatus(is_healthy=False, error="Timeout")
        except httpx.ConnectError as e:
            status = HealthStatus(is_healthy=False, error=str(e))
        except Exception as e:
            status = HealthStatus(is_healthy=False, error=f"Error: {str(e)}")

        # Cache result
        self._cache[url] = status
        return status

    def build_health_url(self, base_url: str, health_endpoint: Optional[str]) -> Optional[str]:
        """Build full health check URL.

        Args:
            base_url: Base URL of service
            health_endpoint: Health endpoint path

        Returns:
            Full URL or None if health_endpoint is None
        """
        if health_endpoint is None:
            return None

        base = base_url.rstrip('/')
        endpoint = health_endpoint if health_endpoint.startswith('/') else f'/{health_endpoint}'
        return f"{base}{endpoint}"

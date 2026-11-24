"""FastAPI application entry point."""
from fastapi import Depends, FastAPI

from src.config import settings
from src.api.dependencies.trusted_host import require_trusted_host
from src.api.routes import health, services, pages
from src.core.database import init_db

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
    # Every route: write requests from an untrusted Host or Origin get 403.
    dependencies=[Depends(require_trusted_host)],
)


@app.on_event("startup")
def startup_event():
    """Initialize database on startup."""
    init_db()


# Include routers
app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
app.include_router(services.router, prefix="/api/services", tags=["services"])
app.include_router(pages.router, tags=["pages"])

"""FastAPI application entry point."""
from fastapi import FastAPI

from src.config import settings
from src.api.routes import health, services, pages
from src.core.database import init_db

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.on_event("startup")
def startup_event():
    """Initialize database on startup."""
    init_db()

# No CORS middleware: the page's own scripts are same-origin and registrations
# come from servers, so no browser on another origin may call the write API.

# Include routers
app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
app.include_router(services.router, prefix="/api/services", tags=["services"])
app.include_router(pages.router, tags=["pages"])

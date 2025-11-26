"""Application configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Application
    app_name: str = "My FastAPI Project"
    version: str = "0.1.0"
    debug: bool = False

    # API
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "sqlite:///./app.db"

    # Security
    secret_key: str = "change-me-in-production-use-secrets"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    class Config:
        """Pydantic config."""
        env_file = ".env"


settings = Settings()

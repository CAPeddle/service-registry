"""Shared test fixtures."""
import os
import tempfile

# Point the app at a throwaway database before anything imports src.config.
# Several test modules call Base.metadata.drop_all(bind=engine); without this
# they would act on ./service_registry.db, which is the live database when the
# suite runs from the deployed checkout.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="service-registry-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_DIR}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.main import app
from src.models.base import Base


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Test database session."""
    # Use in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)

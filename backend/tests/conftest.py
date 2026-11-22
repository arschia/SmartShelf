import os

# Isolate test configuration from any local/production .env file and never touch
# the store database or reuse production secrets during the test suite.
os.environ.update({
    "APP_ENV": "test",
    "SECRET_KEY": "test-only-secret-key-not-for-production-2026-11",
    "ADMIN_PIN": "TestAdminPin#2026",
    "TOKEN_TTL_SECONDS": "28800",
    "STORE_OPEN": "true",
    "ALLOW_INSECURE_TEST_PIN": "false",
    "DB_URL": "sqlite:///:memory:",
})

import onnxruntime as ort
ort.disable_telemetry_events()
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.services.auth import _failed_attempts, _lockout_until

# Use an in-memory SQLite database with StaticPool for thread-safe shared in-memory DB
TEST_DB_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def reset_auth_lockout():
    """Ensure brute force tracking state is reset between tests."""
    _failed_attempts.clear()
    _lockout_until.clear()
    yield
    _failed_attempts.clear()
    _lockout_until.clear()


@pytest.fixture(scope="function")
def db_session():
    """Create fresh database tables for each test and drop them afterwards."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Provide a TestClient with database dependency overridden."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_headers():
    from backend.app.services.auth import create_admin_token
    token = create_admin_token()
    return {"Authorization": f"Bearer {token}"}

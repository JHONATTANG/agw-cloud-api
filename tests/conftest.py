"""
Pytest configuration and shared fixtures for VitalCrop Cloud API tests.
"""
import pytest
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

# Override settings before app import
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_vitalgcrop")
os.environ.setdefault("EDGE_GATEWAY_TOKEN", "test-edge-token-12345")

from app.main import app
from app.core.security import create_access_token, hash_password


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db():
    """Mock asyncpg connection."""
    db = AsyncMock()
    return db


@pytest.fixture
def admin_token():
    return create_access_token({"sub": "00000000-0000-0000-0000-000000000001", "role": "ADMIN"})


@pytest.fixture
def operator_token():
    return create_access_token({"sub": "00000000-0000-0000-0000-000000000002", "role": "OPERATOR"})


@pytest.fixture
def edge_token():
    return "test-edge-token-12345"


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

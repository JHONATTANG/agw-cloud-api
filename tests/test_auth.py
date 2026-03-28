"""
Tests — Authentication endpoints
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    mock_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@vitalcrop.io",
        "role": "ADMIN",
        "is_active": True,
        "hashed_password": "$2b$12$placeholder",
    }
    with patch("app.routers.auth.AuthService") as MockService:
        instance = MockService.return_value
        instance.authenticate = AsyncMock(return_value=mock_user)
        instance.create_tokens = AsyncMock(return_value={
            "access_token": "access.jwt.token",
            "refresh_token": "refresh.jwt.token",
            "token_type": "bearer",
        })
        response = await client.post("/api/auth/login", json={
            "email": "admin@vitalcrop.io",
            "password": "securepassword"
        })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    with patch("app.routers.auth.AuthService") as MockService:
        instance = MockService.return_value
        instance.authenticate = AsyncMock(return_value=None)
        response = await client.post("/api/auth/login", json={
            "email": "wrong@vitalcrop.io",
            "password": "badpassword"
        })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_short_password_validation(client: AsyncClient):
    """Pydantic should reject passwords shorter than 8 chars."""
    response = await client.post("/api/auth/login", json={
        "email": "admin@vitalcrop.io",
        "password": "short"
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

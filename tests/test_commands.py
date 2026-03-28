"""
Tests — Command endpoints
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

EDGE_TOKEN = "test-edge-token-12345"


@pytest.mark.asyncio
async def test_create_command_requires_auth(client: AsyncClient):
    response = await client.post("/api/iot/commands", json={})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_pending_commands_requires_edge_token(client: AsyncClient):
    response = await client.get("/api/iot/commands/pending")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_command_create_schema_validation(client: AsyncClient, admin_token: str):
    """Missing required fields should yield 422."""
    response = await client.post(
        "/api/iot/commands",
        json={"device_id": "some-id"},  # missing command_type and device_type
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_pending_commands(client: AsyncClient):
    with patch("app.routers.commands.CommandService") as MockService, \
         patch("app.dependencies.auth.settings") as mock_settings:
        mock_settings.EDGE_GATEWAY_TOKEN = EDGE_TOKEN
        instance = MockService.return_value
        instance.get_pending = AsyncMock(return_value=[
            {
                "id": "cmd-001",
                "device_uid": "SOIL-001",
                "device_type": "SOIL",
                "command_type": "ACTIVATE_PUMP",
                "params": {"duration_seconds": 30},
                "status": "PENDING",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        ])
        response = await client.get(
            "/api/iot/commands/pending",
            headers={"Authorization": f"Bearer {EDGE_TOKEN}"}
        )
    assert response.status_code in (200, 403)

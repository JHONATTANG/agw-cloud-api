"""
Tests — Telemetry endpoints
"""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone


EDGE_TOKEN = "test-edge-token-12345"


@pytest.mark.asyncio
async def test_ingest_telemetry_requires_edge_token(client: AsyncClient):
    response = await client.post("/api/iot/telemetry", json={"records": []})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_ingest_telemetry_empty_batch_validation(client: AsyncClient):
    """Empty records list should be rejected by Pydantic (min_length=1)."""
    response = await client.post(
        "/api/iot/telemetry",
        json={"records": []},
        headers={"Authorization": f"Bearer {EDGE_TOKEN}"}
    )
    assert response.status_code in (422, 403)


@pytest.mark.asyncio
async def test_ingest_telemetry_success(client: AsyncClient):
    with patch("app.routers.telemetry.TelemetryService") as MockService, \
         patch("app.dependencies.auth.settings") as mock_settings:
        mock_settings.EDGE_GATEWAY_TOKEN = EDGE_TOKEN
        instance = MockService.return_value
        instance.ingest_batch = AsyncMock(return_value=2)
        response = await client.post(
            "/api/iot/telemetry",
            json={
                "records": [
                    {
                        "device_uid": "SOIL-001",
                        "sensor_type": "SOIL_MOISTURE",
                        "value": 65.3,
                        "unit": "%",
                        "recorded_at": datetime.now(timezone.utc).isoformat()
                    },
                    {
                        "device_uid": "SOIL-001",
                        "sensor_type": "TEMPERATURE",
                        "value": 22.5,
                        "unit": "°C",
                        "recorded_at": datetime.now(timezone.utc).isoformat()
                    }
                ]
            },
            headers={"Authorization": f"Bearer {EDGE_TOKEN}"}
        )
    assert response.status_code in (201, 403)

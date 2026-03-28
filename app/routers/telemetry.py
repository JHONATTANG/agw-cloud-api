"""
Router — Telemetry endpoints
"""
from fastapi import APIRouter, Depends, Query
from datetime import datetime
from typing import Optional
from app.schemas.telemetry import TelemetryBatchInput, TelemetryResponse
from app.services.telemetry_service import TelemetryService
from app.dependencies.auth import get_current_user, get_edge_gateway
from app.core.database import get_db
import asyncpg

router = APIRouter(prefix="/api/iot/telemetry", tags=["Telemetry"])


@router.post("", status_code=201)
async def ingest_telemetry(
    payload: TelemetryBatchInput,
    edge=Depends(get_edge_gateway),
    db: asyncpg.Connection = Depends(get_db)
):
    """Edge Gateway ingests telemetry. Accepts batch of up to 100 records."""
    service = TelemetryService(db)
    inserted = await service.ingest_batch(payload.records)
    return {"inserted": inserted, "status": "ok"}


@router.get("/{device_id}/latest")
async def get_latest(
    device_id: str,
    current_user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """Most recent reading for a device."""
    service = TelemetryService(db)
    data = await service.get_latest(device_id, str(current_user["id"]))
    return {"data": data}


@router.get("/{device_id}/history")
async def get_history(
    device_id: str,
    from_ts: Optional[datetime] = Query(None, description="Start of time range (ISO 8601)"),
    to_ts: Optional[datetime] = Query(None, description="End of time range (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000),
    current_user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """Paginated telemetry history with optional date range."""
    service = TelemetryService(db)
    records = await service.get_history(device_id, str(current_user["id"]), from_ts, to_ts, limit)
    return {"data": records, "count": len(records)}

"""
Router — Alert endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
from app.schemas.alert import AlertResponse
from app.dependencies.auth import get_current_user
from app.core.database import get_db
import asyncpg
import uuid

router = APIRouter(prefix="/api/iot/alerts", tags=["Alerts"])


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    current_user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """Lists alerts for devices owned by the current user."""
    query = (
        "SELECT a.id, a.device_uid, a.sensor_type, a.severity, a.title, a.message, "
        "a.threshold_value, a.actual_value, a.is_read, a.triggered_at, a.read_at "
        "FROM alerts a JOIN devices d ON d.device_uid=a.device_uid "
        "WHERE d.owner_id=$1"
    )
    params: list = [uuid.UUID(str(current_user["id"]))]

    if is_read is not None:
        params.append(is_read)
        query += f" AND a.is_read=${len(params)}"
    if severity:
        params.append(severity.upper())
        query += f" AND a.severity=${len(params)}"

    params.append(limit)
    query += f" ORDER BY a.triggered_at DESC LIMIT ${len(params)}"

    rows = await db.fetch(query, *params)
    return [dict(r) for r in rows]


@router.patch("/{alert_id}/read", response_model=AlertResponse)
async def mark_alert_read(
    alert_id: str,
    current_user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """Marks an alert as read."""
    now = datetime.now(timezone.utc)
    row = await db.fetchrow(
        "UPDATE alerts SET is_read=true, read_at=$1 WHERE id=$2 "
        "RETURNING id, device_uid, sensor_type, severity, title, message, "
        "threshold_value, actual_value, is_read, triggered_at, read_at",
        now, uuid.UUID(alert_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return dict(row)

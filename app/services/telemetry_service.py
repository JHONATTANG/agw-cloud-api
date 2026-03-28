"""
Telemetry service — batch ingest and queries
"""
from typing import Optional
import asyncpg
import uuid
from datetime import datetime
from app.schemas.telemetry import TelemetryRecord


class TelemetryService:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def _resolve_device_id(self, device_uid: str) -> Optional[uuid.UUID]:
        row = await self.db.fetchrow(
            "SELECT id FROM devices WHERE device_uid=$1", device_uid
        )
        return row["id"] if row else None

    async def ingest_batch(self, records: list[TelemetryRecord]) -> int:
        """Bulk-insert telemetry records. Returns count of inserted rows."""
        rows = []
        for r in records:
            device_id = await self._resolve_device_id(r.device_uid)
            if not device_id:
                continue  # Skip unknown devices
            rows.append((
                uuid.uuid4(), device_id, r.device_uid,
                r.sensor_type, r.value, r.unit,
                r.raw, r.recorded_at
            ))
        if not rows:
            return 0
        await self.db.executemany(
            "INSERT INTO telemetry (id, device_id, device_uid, sensor_type, value, unit, raw, recorded_at) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            rows
        )
        # Update last_seen_at on device
        device_uids = list({r[2] for r in rows})
        await self.db.execute(
            "UPDATE devices SET last_seen_at=NOW(), status='ONLINE' WHERE device_uid=ANY($1)",
            device_uids
        )
        return len(rows)

    async def get_latest(self, device_id: str, owner_id: str) -> Optional[dict]:
        row = await self.db.fetchrow(
            "SELECT t.id, t.device_uid, t.sensor_type, t.value, t.unit, t.recorded_at, t.ingested_at "
            "FROM telemetry t JOIN devices d ON d.id=t.device_id "
            "WHERE d.id=$1 AND d.owner_id=$2 ORDER BY t.recorded_at DESC LIMIT 1",
            uuid.UUID(device_id), uuid.UUID(owner_id)
        )
        return dict(row) if row else None

    async def get_history(
        self,
        device_id: str,
        owner_id: str,
        from_ts: Optional[datetime],
        to_ts: Optional[datetime],
        limit: int,
    ) -> list[dict]:
        query = (
            "SELECT t.id, t.device_uid, t.sensor_type, t.value, t.unit, t.recorded_at, t.ingested_at "
            "FROM telemetry t JOIN devices d ON d.id=t.device_id "
            "WHERE d.id=$1 AND d.owner_id=$2"
        )
        params: list = [uuid.UUID(device_id), uuid.UUID(owner_id)]
        if from_ts:
            params.append(from_ts)
            query += f" AND t.recorded_at >= ${len(params)}"
        if to_ts:
            params.append(to_ts)
            query += f" AND t.recorded_at <= ${len(params)}"
        params.append(limit)
        query += f" ORDER BY t.recorded_at DESC LIMIT ${len(params)}"
        rows = await self.db.fetch(query, *params)
        return [dict(r) for r in rows]

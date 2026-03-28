"""
Device service — CRUD for IoT devices
"""
from typing import Optional
import asyncpg
import uuid
from app.schemas.device import DeviceCreate, DeviceUpdate


class DeviceService:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def list_devices(self, owner_id: str) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT id, device_uid, name, device_type, status, location, firmware_version, "
            "metadata, last_seen_at, created_at FROM devices WHERE owner_id=$1 ORDER BY created_at DESC",
            uuid.UUID(owner_id)
        )
        return [dict(r) for r in rows]

    async def get_device(self, device_id: str, owner_id: str) -> Optional[dict]:
        row = await self.db.fetchrow(
            "SELECT id, device_uid, name, device_type, status, location, firmware_version, "
            "metadata, last_seen_at, created_at FROM devices WHERE id=$1 AND owner_id=$2",
            uuid.UUID(device_id), uuid.UUID(owner_id)
        )
        return dict(row) if row else None

    async def create_device(self, payload: DeviceCreate, owner_id: str) -> dict:
        row = await self.db.fetchrow(
            "INSERT INTO devices (id, device_uid, name, device_type, owner_id, location, metadata) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7) "
            "RETURNING id, device_uid, name, device_type, status, location, firmware_version, metadata, last_seen_at, created_at",
            uuid.uuid4(), payload.device_uid, payload.name, payload.device_type.value,
            uuid.UUID(owner_id), payload.location, payload.metadata
        )
        return dict(row)

    async def update_device(self, device_id: str, payload: DeviceUpdate, owner_id: str) -> Optional[dict]:
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            return await self.get_device(device_id, owner_id)
        set_clause = ", ".join(f"{k}=${i+3}" for i, k in enumerate(updates.keys()))
        values = list(updates.values())
        row = await self.db.fetchrow(
            f"UPDATE devices SET {set_clause}, updated_at=NOW() WHERE id=$1 AND owner_id=$2 "
            "RETURNING id, device_uid, name, device_type, status, location, firmware_version, metadata, last_seen_at, created_at",
            uuid.UUID(device_id), uuid.UUID(owner_id), *values
        )
        return dict(row) if row else None

    async def delete_device(self, device_id: str) -> bool:
        result = await self.db.execute(
            "DELETE FROM devices WHERE id=$1", uuid.UUID(device_id)
        )
        return result == "DELETE 1"

"""
Command service — create, poll pending, update status
"""
import asyncpg
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.schemas.command import CommandCreate, CommandStatus


class CommandService:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def create(self, payload: CommandCreate, created_by: str) -> dict:
        # Resolve device UUID from device_id string (could be UUID or device_uid)
        try:
            device_uuid = uuid.UUID(payload.device_id)
        except ValueError:
            row = await self.db.fetchrow("SELECT id FROM devices WHERE device_uid=$1", payload.device_id)
            if not row:
                raise ValueError(f"Device not found: {payload.device_id}")
            device_uuid = row["id"]

        device_uid_row = await self.db.fetchrow("SELECT device_uid FROM devices WHERE id=$1", device_uuid)
        device_uid = device_uid_row["device_uid"] if device_uid_row else str(device_uuid)

        row = await self.db.fetchrow(
            "INSERT INTO commands (id, device_id, device_uid, device_type, command_type, params, created_by) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7) "
            "RETURNING id, device_id, device_uid, device_type, command_type, params, status, created_at, executed_at",
            uuid.uuid4(), device_uuid, device_uid, payload.device_type,
            payload.command_type.value, dict(payload.params or {}),
            uuid.UUID(created_by)
        )
        return dict(row)

    async def get_pending(self) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT id, device_id, device_uid, device_type, command_type, params, status, created_at "
            "FROM commands WHERE status='PENDING' ORDER BY created_at ASC"
        )
        return [dict(r) for r in rows]

    async def update_status(
        self, command_id: str, status: CommandStatus, error_message: Optional[str] = None
    ) -> Optional[dict]:
        executed_at = datetime.now(timezone.utc) if status in (CommandStatus.EXECUTED, CommandStatus.FAILED) else None
        row = await self.db.fetchrow(
            "UPDATE commands SET status=$2, executed_at=$3, error_message=$4 WHERE id=$1 "
            "RETURNING id, device_id, device_type, command_type, params, status, created_at, executed_at",
            uuid.UUID(command_id), status.value, executed_at, error_message
        )
        return dict(row) if row else None

    async def get_history(self, owner_id: str, device_id: Optional[str], limit: int) -> list[dict]:
        if device_id:
            rows = await self.db.fetch(
                "SELECT c.id, c.device_uid, c.device_type, c.command_type, c.params, c.status, c.created_at, c.executed_at "
                "FROM commands c JOIN devices d ON d.id=c.device_id "
                "WHERE d.owner_id=$1 AND c.device_id=$2 ORDER BY c.created_at DESC LIMIT $3",
                uuid.UUID(owner_id), uuid.UUID(device_id), limit
            )
        else:
            rows = await self.db.fetch(
                "SELECT c.id, c.device_uid, c.device_type, c.command_type, c.params, c.status, c.created_at, c.executed_at "
                "FROM commands c JOIN devices d ON d.id=c.device_id "
                "WHERE d.owner_id=$1 ORDER BY c.created_at DESC LIMIT $2",
                uuid.UUID(owner_id), limit
            )
        return [dict(r) for r in rows]

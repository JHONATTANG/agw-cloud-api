"""
Router — IoT Command endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from app.schemas.command import CommandCreate, CommandResponse, CommandStatusUpdate
from app.services.command_service import CommandService
from app.dependencies.auth import get_current_user, get_edge_gateway
from app.core.database import get_db
import asyncpg

router = APIRouter(prefix="/api/iot/commands", tags=["Commands"])


@router.post("", response_model=CommandResponse, status_code=201)
async def create_command(
    payload: CommandCreate,
    current_user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """Dashboard creates a command for a device."""
    service = CommandService(db)
    try:
        cmd = await service.create(payload, created_by=str(current_user["id"]))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return cmd


@router.get("/pending")
async def get_pending(
    edge=Depends(get_edge_gateway),
    db: asyncpg.Connection = Depends(get_db)
):
    """Edge Gateway polls for PENDING commands."""
    service = CommandService(db)
    commands = await service.get_pending()
    return {"data": commands}


@router.patch("/{command_id}", response_model=CommandResponse)
async def update_command_status(
    command_id: str,
    payload: CommandStatusUpdate,
    edge=Depends(get_edge_gateway),
    db: asyncpg.Connection = Depends(get_db)
):
    """Edge updates a command status (SENT, EXECUTED, FAILED)."""
    service = CommandService(db)
    updated = await service.update_status(command_id, payload.status, payload.error_message)
    if not updated:
        raise HTTPException(status_code=404, detail="Command not found")
    return updated


@router.get("")
async def list_commands(
    device_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    current_user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    """List command history with optional device filter."""
    service = CommandService(db)
    cmds = await service.get_history(str(current_user["id"]), device_id, limit)
    return {"data": cmds, "count": len(cmds)}

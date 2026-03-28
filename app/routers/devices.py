"""
Router — Device CRUD endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse
from app.services.device_service import DeviceService
from app.dependencies.auth import get_current_user, require_role
from app.core.database import get_db
import asyncpg

router = APIRouter(prefix="/api/iot/devices", tags=["Devices"])


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    current_user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    service = DeviceService(db)
    devices = await service.list_devices(str(current_user["id"]))
    return devices


@router.post("", response_model=DeviceResponse, status_code=201)
async def create_device(
    payload: DeviceCreate,
    current_user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    service = DeviceService(db)
    device = await service.create_device(payload, str(current_user["id"]))
    return device


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    current_user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    service = DeviceService(db)
    device = await service.get_device(device_id, str(current_user["id"]))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    payload: DeviceUpdate,
    current_user=Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db)
):
    service = DeviceService(db)
    device = await service.update_device(device_id, payload, str(current_user["id"]))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    current_user=Depends(require_role("ADMIN")),
    db: asyncpg.Connection = Depends(get_db)
):
    service = DeviceService(db)
    deleted = await service.delete_device(device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found")

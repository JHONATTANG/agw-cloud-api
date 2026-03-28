"""
Pydantic v2 schemas — Device
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class DeviceType(str, Enum):
    SOIL = "SOIL"
    HYDRO = "HYDRO"


class DeviceStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class DeviceCreate(BaseModel):
    device_uid: str = Field(min_length=4, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    device_type: DeviceType
    location: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    firmware_version: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class DeviceResponse(BaseModel):
    id: str
    device_uid: str
    name: str
    device_type: str
    status: str
    location: Optional[str] = None
    firmware_version: Optional[str] = None
    metadata: Optional[dict] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}

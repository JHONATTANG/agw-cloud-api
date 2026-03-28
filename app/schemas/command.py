"""
Pydantic v2 schemas — Command
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class CommandType(str, Enum):
    ACTIVATE_PUMP = "ACTIVATE_PUMP"
    OPEN_VALVE = "OPEN_VALVE"
    CLOSE_VALVE = "CLOSE_VALVE"
    SET_CONFIG = "SET_CONFIG"


class CommandStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class CommandCreate(BaseModel):
    device_id: str
    device_type: str          # SOIL | HYDRO
    command_type: CommandType
    params: Optional[dict[str, Any]] = None


class CommandStatusUpdate(BaseModel):
    status: CommandStatus
    error_message: Optional[str] = None


class CommandResponse(BaseModel):
    id: str
    device_id: str
    device_type: str
    command_type: str
    params: Optional[dict] = None
    status: CommandStatus
    created_at: datetime
    executed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

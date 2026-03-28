"""
Pydantic v2 schemas — Alert
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertResponse(BaseModel):
    id: str
    device_uid: str
    sensor_type: Optional[str] = None
    severity: AlertSeverity
    title: str
    message: Optional[str] = None
    threshold_value: Optional[float] = None
    actual_value: Optional[float] = None
    is_read: bool
    triggered_at: datetime
    read_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

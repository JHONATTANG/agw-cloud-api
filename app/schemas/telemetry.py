"""
Pydantic v2 schemas — Telemetry
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class TelemetryRecord(BaseModel):
    device_uid: str
    sensor_type: str
    value: float
    unit: Optional[str] = None
    raw: Optional[dict[str, Any]] = None
    recorded_at: datetime


class TelemetryBatchInput(BaseModel):
    records: list[TelemetryRecord] = Field(min_length=1, max_length=100)


class TelemetryResponse(BaseModel):
    id: str
    device_uid: str
    sensor_type: str
    value: float
    unit: Optional[str] = None
    recorded_at: datetime
    ingested_at: datetime

    model_config = {"from_attributes": True}

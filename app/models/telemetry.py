"""
SQLAlchemy async ORM model — Telemetry
"""
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base


class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False)
    device_uid = Column(String(64), nullable=False, index=True)
    sensor_type = Column(String(64), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(32), nullable=True)
    raw = Column(JSON, nullable=True)      # Full sensor payload snapshot
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_telemetry_device_recorded", "device_id", "recorded_at"),
    )

"""
SQLAlchemy async ORM model — Alert
"""
from sqlalchemy import Column, String, Boolean, DateTime, Enum, ForeignKey, Text, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.core.database import Base


class AlertSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False)
    device_uid = Column(String(64), nullable=False, index=True)
    sensor_type = Column(String(64), nullable=True)
    severity = Column(Enum(AlertSeverity), nullable=False, default=AlertSeverity.WARNING)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    threshold_value = Column(Float, nullable=True)
    actual_value = Column(Float, nullable=True)
    is_read = Column(Boolean, default=False, index=True)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime(timezone=True), nullable=True)

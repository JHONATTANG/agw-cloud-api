"""
SQLAlchemy async ORM model — IoT Device
"""
from sqlalchemy import Column, String, Boolean, DateTime, Enum, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.core.database import Base


class DeviceType(str, enum.Enum):
    SOIL = "SOIL"
    HYDRO = "HYDRO"


class DeviceStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class Device(Base):
    __tablename__ = "devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_uid = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    device_type = Column(Enum(DeviceType), nullable=False)
    status = Column(Enum(DeviceStatus), default=DeviceStatus.OFFLINE)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    location = Column(String(255), nullable=True)
    firmware_version = Column(String(32), nullable=True)
    metadata = Column(JSON, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

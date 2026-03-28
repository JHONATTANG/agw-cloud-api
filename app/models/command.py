"""
SQLAlchemy async ORM model — IoT Command
"""
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.core.database import Base


class CommandType(str, enum.Enum):
    ACTIVATE_PUMP = "ACTIVATE_PUMP"
    OPEN_VALVE = "OPEN_VALVE"
    CLOSE_VALVE = "CLOSE_VALVE"
    SET_CONFIG = "SET_CONFIG"


class CommandStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class Command(Base):
    __tablename__ = "commands"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False)
    device_uid = Column(String(64), nullable=False)
    device_type = Column(String(16), nullable=False)   # SOIL | HYDRO
    command_type = Column(Enum(CommandType), nullable=False)
    params = Column(JSON, nullable=True)
    status = Column(Enum(CommandStatus), default=CommandStatus.PENDING, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String(512), nullable=True)

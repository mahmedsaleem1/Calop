import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

DEVICE_STATUSES = ("active", "revoked")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked')", name="ck_devices_status"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="ck_devices_name_length"),
        Index("uq_devices_one_active_per_owner", "owner_id", unique=True, postgresql_where=text("status = 'active'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="active")
    firmware_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceApiKey(Base):
    __tablename__ = "device_api_keys"
    __table_args__ = (
        Index(
            "uq_device_api_keys_one_live_per_device", "device_id", unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    key_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    key_prefix: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

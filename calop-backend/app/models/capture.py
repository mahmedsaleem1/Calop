import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.device import Device


class Capture(Base):
    """Raw data from the device: one image + one weight, taken together.
    `id` is the capture_id generated on the ESP32, which makes retries idempotent."""

    __tablename__ = "captures"
    __table_args__ = (Index("ix_captures_device_received", "device_id", "received_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    weight_g: Mapped[float] = mapped_column(Float)
    image_url: Mapped[str] = mapped_column(Text)
    image_public_id: Mapped[str] = mapped_column(String(255))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)
    food_label: Mapped[str | None] = mapped_column(String(255))  # the user's own correction

    device: Mapped["Device"] = relationship(back_populates="captures")

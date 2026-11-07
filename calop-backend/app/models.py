import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    """App-side user row. `id` equals the auth provider's user id, but is NOT a
    foreign key to Supabase's auth schema, so this table moves to plain Postgres as is."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    devices: Mapped[list["Device"]] = relationship(back_populates="owner")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(back_populates="devices")
    captures: Mapped[list["Capture"]] = relationship(back_populates="device")


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

    device: Mapped[Device] = relationship(back_populates="captures")
    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="capture", uselist=False, lazy="joined", cascade="all, delete-orphan"
    )


class Analysis(Base):
    """AI guess for a capture, kept separate from the raw data so it can be re-run or swapped."""

    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    capture_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("captures.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    # PENDING | IDENTIFIED | LOW_CONFIDENCE | SKIPPED | FAILED
    provider: Mapped[str | None] = mapped_column(String(50))
    label: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[float | None] = mapped_column(Float)
    protein_g: Mapped[float | None] = mapped_column(Float)
    carbs_g: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    capture: Mapped[Capture] = relationship(back_populates="analysis")

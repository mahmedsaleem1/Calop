import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'device', 'system', 'ai')", name="ck_events_actor_type"),
        Index("ix_events_entity", "entity_type", "entity_id"),
        Index("ix_events_actor_occurred", "actor_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_type: Mapped[str] = mapped_column(String)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str] = mapped_column(Text)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    data: Mapped[dict | None] = mapped_column(JSONB)

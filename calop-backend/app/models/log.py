import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

RESOLUTIONS = ("auto", "user_selected", "user_corrected")


class FoodLogEntry(Base):
    __tablename__ = "food_log_entries"
    __table_args__ = (
        CheckConstraint("weight_source IN ('measured', 'user_estimate')", name="ck_food_log_entries_weight_source"),
        CheckConstraint(
            "resolution IN ('auto', 'user_selected', 'user_corrected')", name="ck_food_log_entries_resolution"
        ),
        Index("ix_food_log_entries_user_date", "user_id", "local_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    capture_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("captures.id", ondelete="CASCADE"), unique=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"))
    weight_g: Mapped[float] = mapped_column(Numeric(7, 1))
    weight_source: Mapped[str] = mapped_column(String)
    resolution: Mapped[str] = mapped_column(String)
    eaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    local_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    nutrients: Mapped[list["FoodLogEntryNutrient"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, lazy="selectin"
    )


class FoodLogEntryNutrient(Base):
    __tablename__ = "food_log_entry_nutrients"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("food_log_entries.id", ondelete="CASCADE"), primary_key=True
    )
    nutrient_id: Mapped[int] = mapped_column(ForeignKey("nutrients.id"), primary_key=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 3))

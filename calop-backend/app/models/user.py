import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, Uuid, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SEXES = ("male", "female")
ACTIVITY_LEVELS = ("sedentary", "light", "moderate", "active", "very_active")
DIET_TYPES = ("none", "vegetarian")
WEIGHT_ENTRY_SOURCES = ("onboarding", "settings")
GOAL_STATUSES = ("active", "replaced", "achieved")


def check_in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class User(Base):
    """`id` equals the auth provider's user id, but is NOT a foreign key to Supabase's auth schema."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str | None] = mapped_column(Text)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint(check_in("sex", SEXES), name="ck_user_profiles_sex"),
        CheckConstraint(check_in("activity_level", ACTIVITY_LEVELS), name="ck_user_profiles_activity_level"),
        CheckConstraint(check_in("diet_type", DIET_TYPES), name="ck_user_profiles_diet_type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String)
    height_cm: Mapped[float] = mapped_column(Numeric(5, 1))
    activity_level: Mapped[str] = mapped_column(String)
    diet_type: Mapped[str] = mapped_column(String)
    allergies: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    timezone: Mapped[str] = mapped_column(Text, server_default="Asia/Karachi")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WeightEntry(Base):
    __tablename__ = "weight_entries"
    __table_args__ = (
        CheckConstraint(check_in("source", WEIGHT_ENTRY_SOURCES), name="ck_weight_entries_source"),
        Index("ix_weight_entries_user_recorded", "user_id", text("recorded_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    weight_kg: Mapped[float] = mapped_column(Numeric(5, 2))
    source: Mapped[str] = mapped_column(String)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint(check_in("status", GOAL_STATUSES), name="ck_goals_status"),
        Index("uq_goals_one_active_per_user", "user_id", unique=True, postgresql_where=text("status = 'active'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    start_weight_kg: Mapped[float] = mapped_column(Numeric(5, 2))
    target_weight_kg: Mapped[float] = mapped_column(Numeric(5, 2))
    start_date: Mapped[date] = mapped_column(Date)
    target_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NutritionTarget(Base):
    __tablename__ = "nutrition_targets"
    __table_args__ = (Index("ix_nutrition_targets_user_effective", "user_id", text("effective_from DESC")),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    goal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("goals.id"))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    maintenance_kcal: Mapped[float] = mapped_column(Numeric(7, 1))
    daily_adjustment_kcal: Mapped[float] = mapped_column(Numeric(7, 1))
    energy_kcal: Mapped[float] = mapped_column(Numeric(7, 1))
    protein_g: Mapped[float] = mapped_column(Numeric(6, 1))
    fat_g: Mapped[float] = mapped_column(Numeric(6, 1))
    carbohydrate_g: Mapped[float] = mapped_column(Numeric(6, 1))
    floor_applied: Mapped[bool] = mapped_column(Boolean)
    method: Mapped[str] = mapped_column(Text)
    inputs: Mapped[dict] = mapped_column(JSONB)

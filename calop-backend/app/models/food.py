import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, Numeric, SmallInteger, String,
    Text, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

FOOD_KINDS = ("ingredient", "dish", "recipe")
PREPARATION_STATES = ("raw", "cooked", "processed", "unknown")
ALIAS_KINDS = ("source", "local", "common", "spelling")


class FoodSource(Base):
    __tablename__ = "food_sources"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(Text)
    year: Mapped[int] = mapped_column(SmallInteger)
    url: Mapped[str | None] = mapped_column(Text)


class FoodGroup(Base):
    __tablename__ = "food_groups"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(SmallInteger)


class Nutrient(Base):
    __tablename__ = "nutrients"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(SmallInteger)
    is_reported: Mapped[bool] = mapped_column(Boolean)


class Food(Base):
    __tablename__ = "foods"
    __table_args__ = (
        CheckConstraint("kind IN ('ingredient', 'dish', 'recipe')", name="ck_foods_kind"),
        CheckConstraint(
            "preparation_state IN ('raw', 'cooked', 'processed', 'unknown')", name="ck_foods_preparation_state"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("food_sources.id"))
    source_ref: Mapped[str] = mapped_column(Text)
    group_id: Mapped[int] = mapped_column(ForeignKey("food_groups.id"))
    source_name: Mapped[str] = mapped_column(Text)
    source_local_name: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    scientific_name: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String)
    preparation_state: Mapped[str] = mapped_column(String)
    is_matchable: Mapped[bool] = mapped_column(Boolean)
    is_searchable: Mapped[bool] = mapped_column(Boolean)
    quality_flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    ingredients_text: Mapped[str | None] = mapped_column(Text)
    preparation_method: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    group: Mapped[FoodGroup] = relationship(lazy="joined")
    nutrient_rows: Mapped[list["FoodNutrient"]] = relationship(lazy="selectin", cascade="all, delete-orphan")
    aliases: Mapped[list["FoodAlias"]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class FoodNutrient(Base):
    __tablename__ = "food_nutrients"

    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"), primary_key=True)
    nutrient_id: Mapped[int] = mapped_column(ForeignKey("nutrients.id"), primary_key=True)
    amount_per_100g: Mapped[float] = mapped_column(Numeric(10, 3))

    nutrient: Mapped[Nutrient] = relationship(lazy="joined")


class FoodAlias(Base):
    __tablename__ = "food_aliases"
    __table_args__ = (
        CheckConstraint("kind IN ('source', 'local', 'common', 'spelling')", name="ck_food_aliases_kind"),
        UniqueConstraint("food_id", "normalized_alias", name="uq_food_aliases_food_alias"),
        Index("uq_food_aliases_preferred", "normalized_alias", unique=True, postgresql_where=text("is_preferred")),
        Index(
            "ix_food_aliases_trgm", "normalized_alias",
            postgresql_using="gin", postgresql_ops={"normalized_alias": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(Text)
    normalized_alias: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String)
    is_preferred: Mapped[bool] = mapped_column(Boolean)


class FoodSearchMiss(Base):
    __tablename__ = "food_search_misses"
    __table_args__ = (CheckConstraint("context IN ('app_search')", name="ck_food_search_misses_context"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    query: Mapped[str] = mapped_column(Text)
    normalized_query: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(String, default="app_search")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

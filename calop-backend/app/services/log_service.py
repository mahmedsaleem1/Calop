"""Turns a resolved capture into a food log entry, and the log-entry routes' queries."""
import uuid
from collections.abc import Sequence
from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, UnprocessableInputError
from app.models import Capture, Food, FoodLogEntry, FoodLogEntryNutrient, User
from app.services import profile_service
from app.services.event_service import record_event
from app.services.nutrition import compute_nutrition


def lock_capture(db: Session, capture: Capture) -> Capture:
    """Locks the capture row and refreshes it. Recognition and a weight update can arrive at the same time."""
    db.flush()
    return db.scalars(
        select(Capture).where(Capture.id == capture.id).with_for_update().execution_options(populate_existing=True)
    ).one()


def try_log(
    db: Session,
    capture: Capture,
    resolution: str | None,
    actor_type: str = "system",
    actor_id: uuid.UUID | None = None,
) -> FoodLogEntry | None:
    """Logs the capture if it has both a food and a weight. Does not commit: the caller does.
    `resolution=None` keeps the existing entry's resolution (used when only the weight changed)."""
    capture = lock_capture(db, capture)

    if capture.selected_food_id is None:
        return None
    if capture.weight_g is None:
        capture.status = "awaiting_weight"
        return None

    food = db.scalar(select(Food).where(Food.id == capture.selected_food_id))
    entry = db.scalar(select(FoodLogEntry).where(FoodLogEntry.capture_id == capture.id))
    created = entry is None

    eaten_at = capture.captured_at or capture.received_at
    local_date = eaten_at.astimezone(profile_service.user_zone(db, capture.user_id)).date()

    if created:
        entry = FoodLogEntry(
            id=uuid.uuid4(), user_id=capture.user_id, capture_id=capture.id, food_id=food.id,
            weight_g=capture.weight_g, weight_source=capture.weight_source, resolution=resolution or "auto",
            eaten_at=eaten_at, local_date=local_date,
        )
        db.add(entry)
        db.flush()
    else:
        entry.food_id = food.id
        entry.weight_g = capture.weight_g
        entry.weight_source = capture.weight_source
        entry.eaten_at = eaten_at
        entry.local_date = local_date
        if resolution is not None:
            entry.resolution = resolution
        db.execute(delete(FoodLogEntryNutrient).where(FoodLogEntryNutrient.entry_id == entry.id))
        db.expire(entry, ["nutrients"])

    for item in compute_nutrition(food, capture.weight_g).amounts:
        db.add(FoodLogEntryNutrient(entry_id=entry.id, nutrient_id=item.nutrient_id, amount=item.amount))

    capture.status = "logged"
    capture.resolved_at = datetime.now(timezone.utc)
    db.flush()
    db.expire(entry, ["nutrients"])
    record_event(
        db, actor_type, actor_id, "entry.created" if created else "entry.recalculated", "entry", entry.id,
        {"user_id": str(capture.user_id), "capture_id": str(capture.id), "food": food.code,
         "weight_g": str(capture.weight_g), "resolution": entry.resolution},
    )
    return entry


def get_owned_entry(db: Session, owner: User, entry_id: uuid.UUID) -> FoodLogEntry:
    entry = db.scalar(select(FoodLogEntry).where(FoodLogEntry.id == entry_id, FoodLogEntry.user_id == owner.id))
    if entry is None:
        raise NotFoundError("Log entry not found", code="entry_not_found")
    return entry


def list_entries(db: Session, owner: User, date_from: date | None, date_to: date | None) -> Sequence[FoodLogEntry]:
    query = (
        select(FoodLogEntry).join(Capture, Capture.id == FoodLogEntry.capture_id)
        .where(FoodLogEntry.user_id == owner.id, Capture.status == "logged")
    )
    if date_from:
        query = query.where(FoodLogEntry.local_date >= date_from)
    if date_to:
        query = query.where(FoodLogEntry.local_date <= date_to)
    return db.scalars(query.order_by(FoodLogEntry.eaten_at.desc())).all()


def selectable_food(db: Session, food_code: str) -> Food:
    """A food the user may choose: it must exist and be searchable."""
    food = db.scalar(select(Food).where(Food.code == food_code))
    if food is None:
        raise NotFoundError("Food not found", code="food_not_found")
    if not food.is_searchable:
        raise UnprocessableInputError("This food cannot be selected", code="food_not_selectable")
    return food


def correct_entry_food(db: Session, owner: User, entry_id: uuid.UUID, food_code: str) -> tuple[FoodLogEntry, Capture]:
    """'Wrong food?': changes only the food. Weight and time stay."""
    entry = get_owned_entry(db, owner, entry_id)
    food = selectable_food(db, food_code)
    capture = db.get(Capture, entry.capture_id)
    previous = entry.food_id
    capture.selected_food_id = food.id
    entry = try_log(db, capture, "user_corrected", "user", owner.id)
    record_event(db, "user", owner.id, "entry.food_changed", "entry", entry.id,
                 {"user_id": str(owner.id), "from_food_id": previous, "to": food.code})
    db.commit()
    return entry, capture

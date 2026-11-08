"""Questionnaire, weights, goals and the daily nutrition target."""
import uuid
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, UnprocessableInputError
from app.models import Event, Goal, NutritionTarget, User, UserProfile, WeightEntry
from app.services import target_calculator as calc
from app.services.event_service import record_event

DEFAULT_TIMEZONE = "Asia/Karachi"
MIN_AGE = 18  # Gemini's terms require users to be 18 or over


def zone_for(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def get_profile(db: Session, user_id: uuid.UUID) -> UserProfile | None:
    return db.get(UserProfile, user_id)


def user_zone(db: Session, user_id: uuid.UUID) -> ZoneInfo:
    profile = get_profile(db, user_id)
    return zone_for(profile.timezone if profile else None)


def today_for(zone: ZoneInfo) -> date:
    return datetime.now(zone).date()


def latest_weight(db: Session, user_id: uuid.UUID) -> WeightEntry | None:
    return db.scalar(
        select(WeightEntry).where(WeightEntry.user_id == user_id).order_by(WeightEntry.recorded_at.desc()).limit(1)
    )


def active_goal(db: Session, user_id: uuid.UUID) -> Goal | None:
    return db.scalar(select(Goal).where(Goal.user_id == user_id, Goal.status == "active"))


def latest_target(db: Session, user_id: uuid.UUID) -> NutritionTarget | None:
    return db.scalar(
        select(NutritionTarget).where(NutritionTarget.user_id == user_id)
        .order_by(NutritionTarget.effective_from.desc()).limit(1)
    )


def _require_adult(date_of_birth: date, today: date) -> None:
    if calc.age_in_years(date_of_birth, today) < MIN_AGE:
        raise UnprocessableInputError("You must be at least 18 to use Calop", code="under_18")


def _validate_timezone(name: str) -> None:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise UnprocessableInputError("Unknown timezone", code="invalid_timezone")


def _calculate(
    profile: UserProfile, weight_kg: Decimal, target_weight_kg: Decimal, target_date: date, today: date,
    expired_ok: bool,
) -> calc.TargetResult:
    age = calc.age_in_years(profile.date_of_birth, today)
    args = dict(
        sex=profile.sex, age=age, height_cm=Decimal(str(profile.height_cm)), weight_kg=weight_kg,
        activity_level=profile.activity_level, today=today,
    )
    try:
        return calc.calculate_target(target_weight_kg=target_weight_kg, target_date=target_date, **args)
    except calc.InvalidTargetDate:
        if not expired_ok:
            raise UnprocessableInputError("Target date must be in the future", code="invalid_target_date")
        # the deadline of an existing goal has passed: hold maintenance and tell the user
        result = calc.calculate_target(target_weight_kg=weight_kg, target_date=today, **args)
        suggested = today + timedelta(days=max(1, int(abs(target_weight_kg - weight_kg) * 7) + 1))
        result.warnings.append(calc.TargetWarning(
            "goal_expired", "The target date of your goal has passed. Set a new date to get a deficit target.", suggested
        ))
        return result


def _store_target(
    db: Session, user: User, goal: Goal | None, result: calc.TargetResult
) -> NutritionTarget:
    target = NutritionTarget(
        user_id=user.id, goal_id=goal.id if goal else None, effective_from=datetime.now(timezone.utc),
        maintenance_kcal=result.maintenance_kcal, daily_adjustment_kcal=result.daily_adjustment_kcal,
        energy_kcal=result.energy_kcal, protein_g=result.protein_g, fat_g=result.fat_g,
        carbohydrate_g=result.carbohydrate_g, floor_applied=result.floor_applied,
        method=calc.METHOD, inputs=result.inputs,
    )
    db.add(target)
    record_event(db, "system", None, "target.calculated", "user", user.id, {
        "user_id": str(user.id), "energy_kcal": str(result.energy_kcal), "floor_applied": result.floor_applied,
        "warnings": [w.code for w in result.warnings],
    })
    return target


def recalculate_target(db: Session, user: User) -> tuple[NutritionTarget, list[calc.TargetWarning]]:
    """Inserts a new target row from the latest weight. Does not commit: the caller does."""
    profile = get_profile(db, user.id)
    weight = latest_weight(db, user.id)
    if profile is None or weight is None:
        raise ConflictError("Complete the questionnaire first", code="onboarding_required")
    goal = active_goal(db, user.id)
    today = today_for(zone_for(profile.timezone))
    current = Decimal(weight.weight_kg)
    if goal is None:  # no active goal: hold the current weight
        result = _calculate(profile, current, current, today, today, expired_ok=False)
    else:
        result = _calculate(profile, current, Decimal(goal.target_weight_kg), goal.target_date, today, expired_ok=True)
    target = _store_target(db, user, goal, result)
    return target, result.warnings


def complete_onboarding(db: Session, user: User, body) -> tuple[UserProfile, Goal, NutritionTarget, list]:
    if user.onboarding_completed_at is not None:
        raise ConflictError("Onboarding was already completed", code="onboarding_already_completed")
    timezone_name = body.timezone or DEFAULT_TIMEZONE
    _validate_timezone(timezone_name)
    today = today_for(zone_for(timezone_name))
    _require_adult(body.date_of_birth, today)
    if body.date_of_birth > today:
        raise UnprocessableInputError("date_of_birth is in the future", code="invalid_date_of_birth")

    profile = UserProfile(
        user_id=user.id, date_of_birth=body.date_of_birth, sex=body.sex, height_cm=body.height_cm,
        activity_level=body.activity_level, diet_type=body.diet_type, allergies=list(body.allergies),
        timezone=timezone_name,
    )
    weight_kg = Decimal(str(body.weight_kg))
    result = _calculate(
        profile, weight_kg, Decimal(str(body.target_weight_kg)), body.target_date, today, expired_ok=False
    )

    try:
        db.add(profile)
        db.add(WeightEntry(user_id=user.id, weight_kg=weight_kg, source="onboarding"))
        goal = Goal(
            user_id=user.id, start_weight_kg=weight_kg, target_weight_kg=body.target_weight_kg,
            start_date=today, target_date=body.target_date, status="active",
        )
        db.add(goal)
        db.flush()
        target = _store_target(db, user, goal, result)
        user.onboarding_completed_at = datetime.now(timezone.utc)
        record_event(db, "user", user.id, "user.onboarded", "user", user.id, {"user_id": str(user.id)})
        record_event(db, "user", user.id, "weight.recorded", "user", user.id,
                     {"user_id": str(user.id), "weight_kg": str(weight_kg), "source": "onboarding"})
        record_event(db, "user", user.id, "goal.set", "goal", goal.id, {
            "user_id": str(user.id), "target_weight_kg": str(body.target_weight_kg),
            "target_date": body.target_date.isoformat(),
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("Onboarding was already completed", code="onboarding_already_completed")
    return profile, goal, target, result.warnings


def update_profile(db: Session, user: User, changes: dict) -> tuple[UserProfile, NutritionTarget, list]:
    profile = get_profile(db, user.id)
    if profile is None:
        raise ConflictError("Complete the questionnaire first", code="onboarding_required")
    if "timezone" in changes:
        _validate_timezone(changes["timezone"])
    if "date_of_birth" in changes:
        today = today_for(zone_for(changes.get("timezone", profile.timezone)))
        _require_adult(changes["date_of_birth"], today)
    for name, value in changes.items():
        setattr(profile, name, list(value) if name == "allergies" else value)
    target, warnings = recalculate_target(db, user)
    record_event(db, "user", user.id, "profile.updated", "user", user.id,
                 {"user_id": str(user.id), "fields": sorted(changes)})
    db.commit()
    return profile, target, warnings


def add_weight(db: Session, user: User, weight_kg: float) -> tuple[WeightEntry, NutritionTarget, list]:
    if get_profile(db, user.id) is None:
        raise ConflictError("Complete the questionnaire first", code="onboarding_required")
    entry = WeightEntry(user_id=user.id, weight_kg=Decimal(str(weight_kg)), source="settings")
    db.add(entry)
    db.flush()
    record_event(db, "user", user.id, "weight.recorded", "user", user.id,
                 {"user_id": str(user.id), "weight_kg": str(weight_kg), "source": "settings"})

    goal = active_goal(db, user.id)
    if goal is not None:
        goal_type = calc.goal_type_for(Decimal(goal.start_weight_kg), Decimal(goal.target_weight_kg))
        weight, target_weight = Decimal(str(weight_kg)), Decimal(goal.target_weight_kg)
        reached = (goal_type == "lose" and weight <= target_weight) or (goal_type == "gain" and weight >= target_weight)
        if reached:
            goal.status = "achieved"
            goal.ended_at = datetime.now(timezone.utc)
            db.flush()
            record_event(db, "system", None, "goal.achieved", "goal", goal.id, {"user_id": str(user.id)})
    target, warnings = recalculate_target(db, user)
    db.commit()
    db.refresh(entry)
    return entry, target, warnings


def list_weights(db: Session, user: User, date_from: date | None, date_to: date | None) -> Sequence[WeightEntry]:
    zone = user_zone(db, user.id)
    query = select(WeightEntry).where(WeightEntry.user_id == user.id)
    if date_from:
        query = query.where(WeightEntry.recorded_at >= datetime.combine(date_from, time.min, zone))
    if date_to:
        query = query.where(WeightEntry.recorded_at < datetime.combine(date_to + timedelta(days=1), time.min, zone))
    return db.scalars(query.order_by(WeightEntry.recorded_at.desc())).all()


def set_goal(db: Session, user: User, target_weight_kg: float, target_date: date) -> tuple[Goal, NutritionTarget, list]:
    profile = get_profile(db, user.id)
    weight = latest_weight(db, user.id)
    if profile is None or weight is None:
        raise ConflictError("Complete the questionnaire first", code="onboarding_required")
    today = today_for(zone_for(profile.timezone))
    target_weight = Decimal(str(target_weight_kg))
    _calculate(profile, Decimal(weight.weight_kg), target_weight, target_date, today, expired_ok=False)  # validates

    old = active_goal(db, user.id)
    if old is not None:
        old.status = "replaced"
        old.ended_at = datetime.now(timezone.utc)
        db.flush()  # free the "one active goal" index before inserting the new one
        record_event(db, "user", user.id, "goal.replaced", "goal", old.id, {"user_id": str(user.id)})
    goal = Goal(
        user_id=user.id, start_weight_kg=weight.weight_kg, target_weight_kg=target_weight, start_date=today,
        target_date=target_date, status="active",
    )
    db.add(goal)
    db.flush()
    record_event(db, "user", user.id, "goal.set", "goal", goal.id, {
        "user_id": str(user.id), "target_weight_kg": str(target_weight), "target_date": target_date.isoformat(),
    })
    target, warnings = recalculate_target(db, user)
    db.commit()
    return goal, target, warnings


def list_activity(db: Session, user: User, limit: int, offset: int) -> Sequence[Event]:
    mine = or_(Event.actor_id == user.id, Event.data["user_id"].as_string() == str(user.id))
    return db.scalars(
        select(Event).where(mine).order_by(Event.occurred_at.desc(), Event.id.desc()).limit(limit).offset(offset)
    ).all()

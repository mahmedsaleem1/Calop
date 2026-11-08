"""Daily and weekly reports. Only entries whose capture is `logged` count, and only reported nutrients.
Sums are done in SQL."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Capture, FoodLogEntry, FoodLogEntryNutrient, Goal, NutritionTarget, Nutrient, User, WeightEntry,
)
from app.services import log_service, profile_service
from app.services.presenters import entries_out

MACRO_CODES = ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
TARGET_FIELDS = {
    "energy_kcal": "energy_kcal", "protein_g": "protein_g", "fat_g": "fat_g", "carbohydrate_g": "carbohydrate_g",
}


def _target_for_day(db: Session, user_id, day: date, zone) -> NutritionTarget | None:
    end_of_day = datetime.combine(day + timedelta(days=1), time.min, zone)
    return db.scalar(
        select(NutritionTarget).where(NutritionTarget.user_id == user_id, NutritionTarget.effective_from < end_of_day)
        .order_by(NutritionTarget.effective_from.desc()).limit(1)
    )


def _target_dict(target: NutritionTarget | None) -> dict | None:
    if target is None:
        return None
    return {
        "energy_kcal": float(target.energy_kcal), "protein_g": float(target.protein_g), "fat_g": float(target.fat_g),
        "carbohydrate_g": float(target.carbohydrate_g), "floor_applied": target.floor_applied,
    }


def daily_report(db: Session, user: User, day: date | None) -> dict:
    zone = profile_service.user_zone(db, user.id)
    day = day or profile_service.today_for(zone)

    rows = db.execute(
        select(
            Nutrient.id, func.sum(FoodLogEntryNutrient.amount).label("total"),
            func.count(func.distinct(FoodLogEntry.id)).label("entries_with_data"),
        )
        .select_from(FoodLogEntryNutrient)
        .join(FoodLogEntry, FoodLogEntry.id == FoodLogEntryNutrient.entry_id)
        .join(Capture, Capture.id == FoodLogEntry.capture_id)
        .join(Nutrient, Nutrient.id == FoodLogEntryNutrient.nutrient_id)
        .where(FoodLogEntry.user_id == user.id, FoodLogEntry.local_date == day, Capture.status == "logged",
               Nutrient.is_reported)
        .group_by(Nutrient.id)
    ).all()
    aggregates = {r.id: r for r in rows}

    entries = log_service.list_entries(db, user, day, day)
    nutrients = db.scalars(select(Nutrient).where(Nutrient.is_reported).order_by(Nutrient.sort_order)).all()
    totals = []
    by_code: dict[str, Decimal] = {}
    for nutrient in nutrients:
        aggregate = aggregates.get(nutrient.id)
        amount = aggregate.total if aggregate else Decimal(0)
        by_code[nutrient.code] = amount
        totals.append({
            "code": nutrient.code, "name": nutrient.name, "unit": nutrient.unit, "amount": float(amount),
            "entries_with_data": aggregate.entries_with_data if aggregate else 0, "entries_total": len(entries),
        })

    target = _target_for_day(db, user.id, day, zone)
    remaining = None
    if target is not None:
        remaining = {
            code: round(float(Decimal(getattr(target, field)) - by_code.get(code, Decimal(0))), 3)
            for code, field in TARGET_FIELDS.items()
        }
    return {
        "date": day, "target": _target_dict(target), "totals": totals, "remaining": remaining,
        "entries": entries_out(db, entries),
        "estimated_entries": sum(1 for e in entries if e.weight_source == "user_estimate"),
    }


def weekly_report(db: Session, user: User, week_start: date | None) -> dict:
    zone = profile_service.user_zone(db, user.id)
    if week_start is None:
        today = profile_service.today_for(zone)
        week_start = today - timedelta(days=today.weekday())  # Monday
    days = [week_start + timedelta(days=i) for i in range(7)]

    rows = db.execute(
        select(
            FoodLogEntry.local_date, Nutrient.code, func.sum(FoodLogEntryNutrient.amount).label("total"),
        )
        .select_from(FoodLogEntryNutrient)
        .join(FoodLogEntry, FoodLogEntry.id == FoodLogEntryNutrient.entry_id)
        .join(Capture, Capture.id == FoodLogEntry.capture_id)
        .join(Nutrient, Nutrient.id == FoodLogEntryNutrient.nutrient_id)
        .where(FoodLogEntry.user_id == user.id, FoodLogEntry.local_date.in_(days), Capture.status == "logged",
               Nutrient.code.in_(MACRO_CODES))
        .group_by(FoodLogEntry.local_date, Nutrient.code)
    ).all()
    sums: dict[date, dict[str, Decimal]] = defaultdict(dict)
    for r in rows:
        sums[r.local_date][r.code] = r.total

    counts = dict(db.execute(
        select(FoodLogEntry.local_date, func.count(FoodLogEntry.id))
        .join(Capture, Capture.id == FoodLogEntry.capture_id)
        .where(FoodLogEntry.user_id == user.id, FoodLogEntry.local_date.in_(days), Capture.status == "logged")
        .group_by(FoodLogEntry.local_date)
    ).all())

    summaries = []
    for day in days:
        values = sums.get(day, {})
        summaries.append({
            "date": day, "entries": counts.get(day, 0),
            **{code: float(values.get(code, Decimal(0))) for code in MACRO_CODES},
            "target": _target_dict(_target_for_day(db, user.id, day, zone)),
        })

    logged = [s for s in summaries if s["entries"] > 0]
    averages = {
        code: round(sum(s[code] for s in logged) / len(logged), 3) if logged else 0.0 for code in MACRO_CODES
    }

    start = datetime.combine(days[0], time.min, zone)
    end = datetime.combine(days[-1] + timedelta(days=1), time.min, zone)
    weights = db.scalars(
        select(WeightEntry).where(WeightEntry.user_id == user.id, WeightEntry.recorded_at >= start,
                                  WeightEntry.recorded_at < end).order_by(WeightEntry.recorded_at)
    ).all()
    goal = db.scalar(select(Goal).where(Goal.user_id == user.id, Goal.status == "active"))
    latest = profile_service.latest_weight(db, user.id)
    return {
        "week_start": days[0], "week_end": days[-1], "days": summaries, "days_logged": len(logged),
        "averages": averages, "weights": weights,
        "goal": {
            "start_weight_kg": float(goal.start_weight_kg), "target_weight_kg": float(goal.target_weight_kg),
            "target_date": goal.target_date, "latest_weight_kg": float(latest.weight_kg) if latest else None,
        } if goal else None,
    }

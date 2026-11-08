"""Builds the capture and log-entry response shapes. Used by the routes and by WebSocket publishing."""
import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Capture, Food, FoodLogEntry, Nutrient, RecognitionRun
from app.realtime import hub
from app.seeds.nutrient_definitions import REPORTED_CODES
from app.views.capture_views import CandidateOut, CaptureOut
from app.views.food_views import FoodRef, NutrientAmountOut
from app.views.log_views import EntryOut

logger = logging.getLogger(__name__)


def image_route(capture_id: uuid.UUID) -> str:
    return f"/api/v1/captures/{capture_id}/image"


def _nutrient_index(db: Session) -> dict[int, Nutrient]:
    return {n.id: n for n in db.scalars(select(Nutrient))}


def _food_refs(db: Session, ids: set[int]) -> dict[int, FoodRef]:
    if not ids:
        return {}
    rows = db.execute(select(Food.id, Food.code, Food.display_name).where(Food.id.in_(ids))).all()
    return {r.id: FoodRef(code=r.code, display_name=r.display_name) for r in rows}


def entries_out(db: Session, entries: Sequence[FoodLogEntry]) -> list[EntryOut]:
    if not entries:
        return []
    nutrients = _nutrient_index(db)
    foods = _food_refs(db, {e.food_id for e in entries})
    result = []
    for entry in entries:
        rows = sorted(entry.nutrients, key=lambda r: nutrients[r.nutrient_id].sort_order)
        present = {nutrients[r.nutrient_id].code for r in rows}
        result.append(EntryOut(
            id=entry.id, capture_id=entry.capture_id, food=foods[entry.food_id], weight_g=entry.weight_g,
            weight_source=entry.weight_source, resolution=entry.resolution, local_date=entry.local_date,
            nutrients=[
                NutrientAmountOut(
                    code=nutrients[r.nutrient_id].code, name=nutrients[r.nutrient_id].name,
                    unit=nutrients[r.nutrient_id].unit, amount=r.amount,
                )
                for r in rows
            ],
            missing=sorted(REPORTED_CODES - present),
        ))
    return result


def captures_out(db: Session, captures: Sequence[Capture]) -> list[CaptureOut]:
    if not captures:
        return []
    ids = [c.id for c in captures]

    runs = db.scalars(
        select(RecognitionRun).where(RecognitionRun.capture_id.in_(ids), RecognitionRun.status == "succeeded")
        .order_by(RecognitionRun.started_at)
    ).all()
    latest_run = {run.capture_id: run for run in runs}  # later runs overwrite earlier ones

    entries = db.scalars(select(FoodLogEntry).where(FoodLogEntry.capture_id.in_(ids))).all()
    entry_out_by_capture = {e.capture_id: out for e, out in zip(entries, entries_out(db, entries))}

    food_ids = {c.selected_food_id for c in captures if c.selected_food_id}
    for run in latest_run.values():
        food_ids.update(cand.food_id for cand in run.candidates if cand.food_id)
    foods = _food_refs(db, food_ids)

    result = []
    for capture in captures:
        run = latest_run.get(capture.id)
        candidates = [
            CandidateOut(code=foods[c.food_id].code, display_name=foods[c.food_id].display_name, confidence=c.confidence)
            for c in (run.candidates if run else [])
            if c.food_id in foods
        ]
        result.append(CaptureOut(
            id=capture.id, source=capture.source, status=capture.status, weight_g=capture.weight_g,
            weight_source=capture.weight_source, image_status=capture.image_status,
            image_url=image_route(capture.id), captured_at=capture.captured_at, received_at=capture.received_at,
            candidates=candidates, not_in_catalog_label=capture.not_in_catalog_label,
            selected_food=foods.get(capture.selected_food_id) if capture.selected_food_id else None,
            entry=entry_out_by_capture.get(capture.id),
        ))
    return result


def capture_out(db: Session, capture: Capture) -> CaptureOut:
    return captures_out(db, [capture])[0]


def publish_capture(db: Session, capture: Capture) -> None:
    """Pushes the capture to the owner's app. Call after the commit. Never raises: a missed push is
    recovered when the app reloads GET /captures."""
    try:
        db.refresh(capture)
        hub.publish(capture.user_id, {"type": "capture.updated", "capture": capture_out(db, capture).model_dump(mode="json")})
    except Exception:
        logger.exception("Could not publish capture %s", capture.id)


def publish_capture_deleted(user_id: uuid.UUID, capture_id: uuid.UUID) -> None:
    hub.publish(user_id, {"type": "capture.deleted", "id": str(capture_id)})

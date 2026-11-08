import hashlib
import io
import logging
import os
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO

import piexif
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import wakeup
from app.core.config import Settings
from app.core.exceptions import (
    ConflictError, NotFoundError, PayloadTooLargeError, UnprocessableInputError, UnsupportedMediaTypeError,
)
from app.integrations.storage.image_storage import ImageStorage, StorageError
from app.models import Capture, Device, FoodLogEntry, User
from app.services import image_service, job_service, log_service, recognition_service
from app.services.event_service import record_event

logger = logging.getLogger(__name__)

JPEG_MAGIC_BYTES = b"\xff\xd8\xff"
MAX_WEIGHT_G = 50000
CLOCK_FUTURE_TOLERANCE = timedelta(minutes=5)
CLOCK_PAST_TOLERANCE = timedelta(days=7)

OPEN_STATUSES_FOR_DISCARD = ("needs_review", "awaiting_weight", "failed")


# ---- ingest ----

def parse_capture_id(value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise UnprocessableInputError("capture_id must be a UUID", code="invalid_capture_id")


def read_jpeg(image_file: BinaryIO, max_bytes: int) -> bytes:
    data = image_file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise PayloadTooLargeError("Image too large", code="image_too_large")
    if data[:3] != JPEG_MAGIC_BYTES:
        raise UnsupportedMediaTypeError("Only JPEG images are accepted", code="jpeg_required")
    return data


def strip_gps(data: bytes) -> bytes:
    """Removes GPS metadata without touching a single pixel. On any failure the original bytes are kept."""
    try:
        exif = piexif.load(data)
        if not exif.get("GPS"):
            return data
        exif["GPS"] = {}
        out = io.BytesIO()
        piexif.insert(piexif.dump(exif), data, out)
        return out.getvalue()
    except Exception:
        logger.warning("Could not strip GPS metadata; keeping the original image", exc_info=True)
        return data


def check_weight(weight_g: float | None, required: bool) -> float | None:
    if weight_g is None:
        if required:
            raise UnprocessableInputError("weight_g is required", code="invalid_weight")
        return None
    if not (0 < weight_g <= MAX_WEIGHT_G):
        raise UnprocessableInputError(f"weight_g must be greater than 0 and at most {MAX_WEIGHT_G}", code="invalid_weight")
    return weight_g


def plausible_captured_at(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if value > now + CLOCK_FUTURE_TOLERANCE or value < now - CLOCK_PAST_TOLERANCE:
        return None
    return value


def write_image(directory: str, capture_id: uuid.UUID, data: bytes) -> Path:
    folder = Path(directory).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / f"{capture_id}.jpg"
    temporary = folder / f"{capture_id}.jpg.tmp-{uuid.uuid4().hex}"
    temporary.write_bytes(data)
    os.replace(temporary, final)
    return final


def _existing_for(existing: Capture, user: User, device: Device | None) -> Capture:
    same_owner = existing.user_id == user.id
    same_device = device is None or existing.device_id == device.id
    same_source = (existing.source == "device") == (device is not None)
    if not (same_owner and same_device and same_source):
        raise ConflictError("capture_id is already used", code="capture_id_in_use")
    return existing


def ingest_capture(
    db: Session,
    settings: Settings,
    user: User,
    device: Device | None,
    requested_capture_id: str | None,
    weight_g: float | None,
    image_file: BinaryIO,
    captured_at: datetime | None,
    app_version: str | None = None,
) -> tuple[Capture, bool]:
    """Shared by device and phone uploads. Returns (capture, created); created is False for a retry."""
    source = "device" if device is not None else "phone"
    capture_id = parse_capture_id(requested_capture_id)

    existing = db.get(Capture, capture_id)  # retries are answered before the image is read
    if existing is not None:
        return _existing_for(existing, user, device), False

    limit = settings.max_device_image_bytes if source == "device" else settings.max_phone_image_bytes
    data = read_jpeg(image_file, limit)
    if source == "phone":
        data = strip_gps(data)
    weight_g = check_weight(weight_g, required=source == "device")
    captured_at = plausible_captured_at(captured_at)

    path = write_image(settings.local_image_dir, capture_id, data)
    try:
        capture = Capture(
            id=capture_id, user_id=user.id, source=source, device_id=device.id if device else None,
            weight_g=weight_g, weight_source="measured" if device else "user_estimate", status="identifying",
            image_status="local", image_local_path=str(path), image_bytes=len(data),
            image_sha256=hashlib.sha256(data).hexdigest(), captured_at=captured_at,
            firmware_version=device.firmware_version if device else None, app_version=app_version,
        )
        db.add(capture)
        db.flush()
        job_service.enqueue(db, "recognize_capture", capture_id, recognition_service.MAX_ATTEMPTS)
        job_service.enqueue(db, "upload_image", capture_id, image_service.MAX_ATTEMPTS)
        record_event(
            db, "device" if device else "user", device.id if device else user.id, "capture.received", "capture",
            capture_id, {"user_id": str(user.id), "source": source, "bytes": len(data)},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(Capture, capture_id)  # a concurrent retry won the race: keep the shared file
        if existing is not None:
            return _existing_for(existing, user, device), False
        image_service.delete_local_file(str(path))
        raise
    except Exception:
        db.rollback()
        image_service.delete_local_file(str(path))
        raise

    db.refresh(capture)
    wakeup.wake()
    return capture, True


# ---- reads ----

def get_owned_capture(db: Session, owner: User, capture_id: uuid.UUID) -> Capture:
    capture = db.scalar(select(Capture).where(Capture.id == capture_id, Capture.user_id == owner.id))
    if capture is None:
        raise NotFoundError("Capture not found", code="capture_not_found")
    return capture


def get_device_capture(db: Session, device: Device, capture_id: uuid.UUID) -> Capture:
    capture = db.scalar(select(Capture).where(Capture.id == capture_id, Capture.device_id == device.id))
    if capture is None:
        raise NotFoundError("Capture not found", code="capture_not_found")
    return capture


def list_owned_captures(
    db: Session, owner: User, status: str | None, source: str | None, date_from: datetime | None,
    date_to: datetime | None, limit: int, offset: int,
) -> tuple[Sequence[Capture], int]:
    query = select(Capture).where(Capture.user_id == owner.id)
    if status:
        query = query.where(Capture.status == status)
    if source:
        query = query.where(Capture.source == source)
    if date_from:
        query = query.where(Capture.received_at >= date_from)
    if date_to:
        query = query.where(Capture.received_at <= date_to)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    captures = db.scalars(query.order_by(Capture.received_at.desc()).limit(limit).offset(offset)).all()
    return captures, total


# ---- changes ----

def change_weight(db: Session, owner: User, capture_id: uuid.UUID, weight_g: float) -> Capture:
    capture = get_owned_capture(db, owner, capture_id)
    if capture.source == "device":
        raise ConflictError("A device weight is measured and cannot be edited", code="weight_locked")
    if capture.status == "discarded":
        raise ConflictError("This capture was discarded", code="capture_discarded")
    check_weight(weight_g, required=True)
    capture.weight_g = weight_g
    record_event(db, "user", owner.id, "capture.weight_changed", "capture", capture.id,
                 {"user_id": str(owner.id), "weight_g": weight_g})
    log_service.try_log(db, capture, None, "user", owner.id)  # keeps the existing resolution
    db.commit()
    return capture


def select_food(db: Session, owner: User, capture_id: uuid.UUID, food_code: str) -> Capture:
    capture = get_owned_capture(db, owner, capture_id)
    if capture.status not in ("needs_review", "awaiting_weight"):
        raise ConflictError("This capture is not waiting for a food", code="invalid_state")
    food = log_service.selectable_food(db, food_code)
    capture.selected_food_id = food.id
    record_event(db, "user", owner.id, "capture.food_selected", "capture", capture.id,
                 {"user_id": str(owner.id), "food": food.code})
    log_service.try_log(db, capture, "user_selected", "user", owner.id)
    db.commit()
    return capture


def discard(db: Session, owner: User, capture_id: uuid.UUID) -> Capture:
    capture = log_service.lock_capture(db, get_owned_capture(db, owner, capture_id))
    if capture.status not in OPEN_STATUSES_FOR_DISCARD:
        raise ConflictError("This capture cannot be discarded", code="invalid_state")
    capture.status = "discarded"
    capture.resolved_at = datetime.now(timezone.utc)
    record_event(db, "user", owner.id, "capture.discarded", "capture", capture.id, {"user_id": str(owner.id)})
    db.commit()
    return capture


def reprocess(db: Session, owner: User, capture_id: uuid.UUID) -> Capture:
    capture = log_service.lock_capture(db, get_owned_capture(db, owner, capture_id))
    if capture.status not in ("failed", "needs_review"):
        raise ConflictError("This capture cannot be reprocessed", code="invalid_state")
    capture.status = "identifying"
    capture.selected_food_id = None
    capture.not_in_catalog_label = None
    job_service.enqueue(db, "recognize_capture", capture.id, recognition_service.MAX_ATTEMPTS)
    record_event(db, "user", owner.id, "capture.reprocessed", "capture", capture.id, {"user_id": str(owner.id)})
    db.commit()
    wakeup.wake()
    return capture


def delete_owned_capture(db: Session, owner: User, capture_id: uuid.UUID, image_storage: ImageStorage) -> None:
    capture = get_owned_capture(db, owner, capture_id)
    local_path, public_id = capture.image_local_path, capture.image_public_id
    db.delete(capture)
    record_event(db, "user", owner.id, "capture.deleted", "capture", capture_id, {"user_id": str(owner.id)})
    db.commit()  # the database row goes first, then the files
    image_service.delete_local_file(local_path)
    if public_id:
        try:
            image_storage.delete(public_id)
        except StorageError:
            logger.exception("Could not delete image %s from storage", public_id)


def entry_for_capture(db: Session, capture: Capture) -> FoodLogEntry | None:
    return db.scalar(select(FoodLogEntry).where(FoodLogEntry.capture_id == capture.id))


DEVICE_STATUS = {
    "identifying": "processing",
    "needs_review": "needs_review",
    "awaiting_weight": "needs_review",
    "logged": "logged",
    "failed": "failed",
    "discarded": "discarded",
}

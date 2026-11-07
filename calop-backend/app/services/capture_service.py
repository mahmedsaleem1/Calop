import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BadGatewayError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    UnprocessableInputError,
    UnsupportedMediaTypeError,
)
from app.integrations.storage.image_storage import ImageStorage, StorageError
from app.models import Capture, Device, User

logger = logging.getLogger(__name__)

JPEG_MAGIC_BYTES = b"\xff\xd8\xff"


def _resolve_capture_id(requested_capture_id: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(requested_capture_id) if requested_capture_id else uuid.uuid4()
    except ValueError:
        return uuid.uuid4()


def _read_validated_jpeg(image_file: BinaryIO, max_image_bytes: int) -> bytes:
    image_bytes = image_file.read(max_image_bytes + 1)
    if len(image_bytes) > max_image_bytes:
        raise PayloadTooLargeError("Image too large")
    if image_bytes[:3] != JPEG_MAGIC_BYTES:
        raise UnsupportedMediaTypeError("Only JPEG images are accepted")
    return image_bytes


def ingest_capture(
    db: Session,
    device: Device,
    weight_g: float,
    image_file: BinaryIO,
    requested_capture_id: str | None,
    image_storage: ImageStorage,
    max_image_bytes: int,
) -> Capture:
    capture_id = _resolve_capture_id(requested_capture_id)

    existing_capture = db.get(Capture, capture_id)
    if existing_capture is not None:
        if existing_capture.device_id != device.id:
            raise ConflictError("capture_id already used")
        return existing_capture

    image_bytes = _read_validated_jpeg(image_file, max_image_bytes)

    try:
        stored_image = image_storage.upload(image_bytes)
    except StorageError:
        logger.exception("Image upload failed")
        raise BadGatewayError("Image storage failed")

    capture = Capture(
        id=capture_id, device_id=device.id, weight_g=weight_g,
        image_url=stored_image.url, image_public_id=stored_image.public_id,
    )
    try:
        db.add(capture)
        db.commit()
        db.refresh(capture)
    except Exception:
        db.rollback()
        try:
            image_storage.delete(stored_image.public_id)
        except StorageError:
            logger.exception("Could not clean up image %s", stored_image.public_id)
        raise

    return capture


def list_owned_captures(
    db: Session,
    owner: User,
    date_from: datetime | None,
    date_to: datetime | None,
    device_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[Capture], int]:
    """Returns one page of captures (newest first) and the total count across all pages."""
    query = select(Capture).join(Device).where(Device.owner_id == owner.id)
    if date_from:
        query = query.where(Capture.received_at >= date_from)
    if date_to:
        query = query.where(Capture.received_at <= date_to)
    if device_id:
        query = query.where(Capture.device_id == device_id)

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    captures = db.scalars(query.order_by(Capture.received_at.desc()).limit(limit).offset(offset)).all()
    return captures, total


def get_owned_capture(db: Session, owner: User, capture_id: uuid.UUID) -> Capture:
    capture = db.scalar(
        select(Capture).join(Device).where(Capture.id == capture_id, Device.owner_id == owner.id)
    )
    if capture is None:
        raise NotFoundError("Capture not found")
    return capture


def update_owned_capture(db: Session, owner: User, capture_id: uuid.UUID, changes: dict[str, Any]) -> Capture:
    capture = get_owned_capture(db, owner, capture_id)
    if "weight_g" in changes and changes["weight_g"] is None:
        raise UnprocessableInputError("weight_g cannot be null")
    for field_name, value in changes.items():
        setattr(capture, field_name, value)
    db.commit()
    db.refresh(capture)
    return capture


def delete_owned_capture(db: Session, owner: User, capture_id: uuid.UUID, image_storage: ImageStorage) -> None:
    capture = get_owned_capture(db, owner, capture_id)
    image_public_id = capture.image_public_id
    db.delete(capture)
    db.commit()
    try:
        image_storage.delete(image_public_id)
    except StorageError:
        logger.exception("Could not delete image %s from storage", image_public_id)

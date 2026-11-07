import logging
import uuid
from datetime import datetime

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.base import FoodAnalyzer
from app.analysis.service import run_analysis
from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_analyzer, get_current_user, get_device, get_storage
from app.models import Analysis, Capture, Device, User
from app.schemas import CaptureList, CaptureOut, CaptureUpdate
from app.storage.base import ImageStorage, StorageError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/captures", tags=["captures"])


def _get_owned(db: Session, user: User, capture_id: uuid.UUID) -> Capture:
    capture = db.scalar(
        select(Capture).join(Device).where(Capture.id == capture_id, Device.owner_id == user.id)
    )
    if capture is None:
        raise HTTPException(404, "Capture not found")
    return capture


@router.post("", response_model=CaptureOut)
def create_capture(
    background: BackgroundTasks,
    weight: float = Form(..., ge=-100, le=50000),
    image: UploadFile = File(...),
    capture_id: str | None = Form(None),
    device_id: str | None = Form(None),  # legacy field from the ESP32; the device is identified by its API key
    device: Device = Depends(get_device),
    db: Session = Depends(get_db),
    storage: ImageStorage = Depends(get_storage),
    analyzer: FoodAnalyzer | None = Depends(get_analyzer),
    settings: Settings = Depends(get_settings),
):
    """Called by the ESP32: image + weight taken together. Sending the same capture_id
    again returns the stored capture instead of creating a duplicate."""
    try:
        cid = uuid.UUID(capture_id) if capture_id else uuid.uuid4()
    except ValueError:
        cid = uuid.uuid4()

    existing = db.get(Capture, cid)
    if existing is not None:
        if existing.device_id != device.id:
            raise HTTPException(409, "capture_id already used")
        return existing

    data = image.file.read(settings.max_image_bytes + 1)
    if len(data) > settings.max_image_bytes:
        raise HTTPException(413, "Image too large")
    if data[:3] != b"\xff\xd8\xff":
        raise HTTPException(415, "Only JPEG images are accepted")

    try:
        stored = storage.upload(data)
    except StorageError:
        log.exception("Image upload failed")
        raise HTTPException(502, "Image storage failed")

    capture = Capture(
        id=cid, device_id=device.id, weight_g=weight,
        image_url=stored.url, image_public_id=stored.public_id,
    )
    if analyzer is not None:
        capture.analysis = Analysis(status="PENDING")
    try:
        db.add(capture)
        db.commit()
        db.refresh(capture)
    except Exception:
        db.rollback()
        try:
            storage.delete(stored.public_id)
        except StorageError:
            log.exception("Could not clean up image %s", stored.public_id)
        raise

    if analyzer is not None:
        background.add_task(run_analysis, capture.id, analyzer, data)
    return capture


@router.get("", response_model=CaptureList)
def list_captures(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    device_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(Capture).join(Device).where(Device.owner_id == user.id)
    if date_from:
        q = q.where(Capture.received_at >= date_from)
    if date_to:
        q = q.where(Capture.received_at <= date_to)
    if device_id:
        q = q.where(Capture.device_id == device_id)

    total = db.scalar(select(func.count()).select_from(q.subquery()))
    items = db.scalars(q.order_by(Capture.received_at.desc()).limit(limit).offset(offset)).unique().all()
    return CaptureList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{capture_id}", response_model=CaptureOut)
def get_capture(capture_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_owned(db, user, capture_id)


@router.patch("/{capture_id}", response_model=CaptureOut)
def update_capture(
    capture_id: uuid.UUID,
    body: CaptureUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    capture = _get_owned(db, user, capture_id)
    changes = body.model_dump(exclude_unset=True)
    if "weight_g" in changes and changes["weight_g"] is None:
        raise HTTPException(422, "weight_g cannot be null")
    for field, value in changes.items():
        setattr(capture, field, value)
    db.commit()
    db.refresh(capture)
    return capture


@router.post("/{capture_id}/analyze", response_model=CaptureOut, status_code=202)
def reanalyze_capture(
    capture_id: uuid.UUID,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    analyzer: FoodAnalyzer | None = Depends(get_analyzer),
):
    """Re-run the AI step (after a failure, a low-confidence result, or a weight correction)."""
    if analyzer is None:
        raise HTTPException(503, "AI analysis is not configured")
    capture = _get_owned(db, user, capture_id)
    if capture.analysis is None:
        capture.analysis = Analysis(status="PENDING")
    else:
        a = capture.analysis
        a.status, a.error, a.completed_at = "PENDING", None, None
    db.commit()
    db.refresh(capture)
    background.add_task(run_analysis, capture.id, analyzer, None)
    return capture


@router.delete("/{capture_id}", status_code=204)
def delete_capture(
    capture_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: ImageStorage = Depends(get_storage),
):
    capture = _get_owned(db, user, capture_id)
    public_id = capture.image_public_id
    db.delete(capture)
    db.commit()
    try:
        storage.delete(public_id)
    except StorageError:
        log.exception("Could not delete image %s from storage", public_id)
    return Response(status_code=204)

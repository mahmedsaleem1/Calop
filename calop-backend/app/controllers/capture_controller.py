import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.controllers.dependencies import get_current_user, get_image_storage
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.integrations.storage.image_storage import ImageStorage
from app.models import User
from app.services import capture_service, presenters
from app.views.capture_views import CaptureList, CaptureOut, CaptureWeightUpdate, SelectFoodIn

router = APIRouter(prefix="/api/v1/captures", tags=["captures"])


def _respond(db: Session, capture):
    presenters.publish_capture(db, capture)
    return presenters.capture_out(db, capture)


@router.post("", response_model=CaptureOut, status_code=202)
def create_phone_capture(
    response: Response,
    image: UploadFile = File(...),
    capture_id: str | None = Form(None),
    weight_g: float | None = Form(None),
    captured_at: datetime | None = Form(None),
    x_app_version: str | None = Header(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """A photo taken with the phone camera. The weight is the user's estimate and may be sent later with PATCH.
    202 for a new capture, 200 when the same capture_id is sent again."""
    capture, created = capture_service.ingest_capture(
        db, settings, current_user, None, capture_id, weight_g, image.file, captured_at, x_app_version
    )
    response.status_code = 202 if created else 200
    if created:
        presenters.publish_capture(db, capture)
    return presenters.capture_out(db, capture)


@router.get("", response_model=CaptureList)
def list_captures(
    status: Literal["identifying", "awaiting_weight", "needs_review", "logged", "discarded", "failed"] | None = None,
    source: Literal["device", "phone"] | None = None,
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    captures, total = capture_service.list_owned_captures(
        db, current_user, status, source, date_from, date_to, limit, offset
    )
    return CaptureList(items=presenters.captures_out(db, captures), total=total, limit=limit, offset=offset)


@router.get("/{capture_id}", response_model=CaptureOut)
def get_capture(capture_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return presenters.capture_out(db, capture_service.get_owned_capture(db, current_user, capture_id))


@router.get("/{capture_id}/image")
def get_capture_image(capture_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The photo: redirects to Cloudinary once uploaded, otherwise served from local disk."""
    capture = capture_service.get_owned_capture(db, current_user, capture_id)
    if capture.image_status == "uploaded" and capture.image_url:
        return RedirectResponse(capture.image_url, status_code=307)
    if capture.image_local_path and Path(capture.image_local_path).is_file():
        return FileResponse(capture.image_local_path, media_type="image/jpeg")
    if capture.image_url:  # uploaded between the two checks
        return RedirectResponse(capture.image_url, status_code=307)
    raise NotFoundError("Image not found", code="image_not_found")


@router.patch("/{capture_id}", response_model=CaptureOut)
def update_capture_weight(
    capture_id: uuid.UUID,
    body: CaptureWeightUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sets the estimated weight of a phone capture. Device weights are measured and locked."""
    return _respond(db, capture_service.change_weight(db, current_user, capture_id, body.weight_g))


@router.post("/{capture_id}/select", response_model=CaptureOut)
def select_capture_food(
    capture_id: uuid.UUID, body: SelectFoodIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """The user picks a food from the candidates or the search results."""
    return _respond(db, capture_service.select_food(db, current_user, capture_id, body.food_code))


@router.post("/{capture_id}/discard", response_model=CaptureOut)
def discard_capture(capture_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Kept on record but never counted in reports."""
    return _respond(db, capture_service.discard(db, current_user, capture_id))


@router.post("/{capture_id}/reprocess", response_model=CaptureOut)
def reprocess_capture(capture_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Runs the AI recognition again."""
    return _respond(db, capture_service.reprocess(db, current_user, capture_id))


@router.delete("/{capture_id}", status_code=204)
def delete_capture(
    capture_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    image_storage: ImageStorage = Depends(get_image_storage),
):
    """Deletes the capture, its log entry and its photo."""
    capture_service.delete_owned_capture(db, current_user, capture_id, image_storage)
    presenters.publish_capture_deleted(current_user.id, capture_id)
    return Response(status_code=204)

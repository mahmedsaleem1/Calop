import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.controllers.dependencies import get_authenticated_device, get_current_user, get_image_storage
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.integrations.storage.image_storage import ImageStorage
from app.models import Device, User
from app.services import capture_service
from app.views.capture_views import CaptureList, CaptureOut, CaptureUpdate

router = APIRouter(prefix="/api/captures", tags=["captures"])


@router.post("", response_model=CaptureOut)
def create_capture(
    weight: float = Form(..., ge=-100, le=50000),
    image: UploadFile = File(...),
    capture_id: str | None = Form(None),
    device_id: str | None = Form(None),  # legacy field from the ESP32; the device is identified by its API key
    device: Device = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
    image_storage: ImageStorage = Depends(get_image_storage),
    settings: Settings = Depends(get_settings),
):
    """Called by the ESP32: image + weight taken together. Sending the same capture_id
    again returns the stored capture instead of creating a duplicate."""
    return capture_service.ingest_capture(
        db=db,
        device=device,
        weight_g=weight,
        image_file=image.file,
        requested_capture_id=capture_id,
        image_storage=image_storage,
        max_image_bytes=settings.max_image_bytes,
    )


@router.get("", response_model=CaptureList)
def list_captures(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    device_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    captures, total = capture_service.list_owned_captures(
        db, current_user, date_from, date_to, device_id, limit, offset
    )
    return CaptureList(items=captures, total=total, limit=limit, offset=offset)


@router.get("/{capture_id}", response_model=CaptureOut)
def get_capture(capture_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return capture_service.get_owned_capture(db, current_user, capture_id)


@router.patch("/{capture_id}", response_model=CaptureOut)
def update_capture(
    capture_id: uuid.UUID,
    body: CaptureUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return capture_service.update_owned_capture(db, current_user, capture_id, body.model_dump(exclude_unset=True))


@router.delete("/{capture_id}", status_code=204)
def delete_capture(
    capture_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    image_storage: ImageStorage = Depends(get_image_storage),
):
    capture_service.delete_owned_capture(db, current_user, capture_id, image_storage)
    return Response(status_code=204)

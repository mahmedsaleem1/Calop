import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.controllers.dependencies import get_authenticated_device
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models import Device, User
from app.services import capture_service, presenters
from app.views.capture_views import CaptureOut, DeviceCaptureStatusOut

router = APIRouter(prefix="/api/v1/device", tags=["device"])


@router.post("/captures", response_model=CaptureOut, status_code=202)
def create_device_capture(
    response: Response,
    image: UploadFile = File(...),
    capture_id: str | None = Form(None),
    weight_g: float | None = Form(None),
    captured_at: datetime | None = Form(None),
    device: Device = Depends(get_authenticated_device),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Called by the ESP32: a JPEG and the weight on the scale. 202 for a new capture, 200 when the same
    capture_id is sent again."""
    owner = db.get(User, device.owner_id)
    capture, created = capture_service.ingest_capture(
        db, settings, owner, device, capture_id, weight_g, image.file, captured_at
    )
    response.status_code = 202 if created else 200
    if created:
        presenters.publish_capture(db, capture)
    return presenters.capture_out(db, capture)


@router.get("/captures/{capture_id}/status", response_model=DeviceCaptureStatusOut)
def get_device_capture_status(
    capture_id: uuid.UUID, device: Device = Depends(get_authenticated_device), db: Session = Depends(get_db)
):
    """Polled by the ESP32 after an upload."""
    capture = capture_service.get_device_capture(db, device, capture_id)
    return DeviceCaptureStatusOut(status=capture_service.DEVICE_STATUS[capture.status])

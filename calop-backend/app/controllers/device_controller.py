import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.controllers.dependencies import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import device_service
from app.views.device_views import ApiKeyOut, DeviceCreate, DeviceCreated, DeviceOut, DeviceUpdate, build_device_created

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.post("", response_model=DeviceCreated, status_code=201)
def create_device(body: DeviceCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pairs the user's one device. The API key is returned once, for flashing the firmware."""
    device, api_key = device_service.create_device(db, current_user, body.name)
    return build_device_created(device, api_key)


@router.get("", response_model=list[DeviceOut])
def list_devices(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return device_service.list_devices(db, current_user)


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return device_service.get_owned_device(db, current_user, device_id)


@router.patch("/{device_id}", response_model=DeviceOut)
def rename_device(
    device_id: uuid.UUID, body: DeviceUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return device_service.rename_device(db, current_user, device_id, body.name)


@router.post("/{device_id}/rotate-key", response_model=ApiKeyOut)
def rotate_device_key(device_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revokes the current key and returns a new one, once."""
    return ApiKeyOut(api_key=device_service.rotate_key(db, current_user, device_id))


@router.delete("/{device_id}", status_code=204)
def revoke_device(device_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revokes the device. Its captures stay."""
    device_service.revoke_device(db, current_user, device_id)
    return Response(status_code=204)

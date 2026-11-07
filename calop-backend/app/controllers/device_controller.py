import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.controllers.dependencies import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import device_service
from app.views.device_views import DeviceCreate, DeviceCreated, DeviceOut, build_device_created

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post("", response_model=DeviceCreated, status_code=201)
def create_device(body: DeviceCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device, api_key = device_service.create_device(db, current_user, body.name)
    return build_device_created(device, api_key)


@router.get("", response_model=list[DeviceOut])
def list_devices(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return device_service.list_devices(db, current_user)


@router.delete("/{device_id}", status_code=204)
def delete_device(device_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device_service.delete_device(db, current_user, device_id)
    return Response(status_code=204)

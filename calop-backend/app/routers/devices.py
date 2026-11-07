import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Device, User
from app.schemas import DeviceCreate, DeviceCreated, DeviceOut
from app.security import hash_api_key

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post("", response_model=DeviceCreated, status_code=201)
def create_device(body: DeviceCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    api_key = secrets.token_urlsafe(32)
    device = Device(owner_id=user.id, name=body.name, api_key_hash=hash_api_key(api_key))
    db.add(device)
    db.commit()
    db.refresh(device)
    return DeviceCreated(**DeviceOut.model_validate(device).model_dump(), api_key=api_key)


@router.get("", response_model=list[DeviceOut])
def list_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Device).where(Device.owner_id == user.id).order_by(Device.created_at)).all()


@router.delete("/{device_id}", status_code=204)
def delete_device(device_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = db.scalar(select(Device).where(Device.id == device_id, Device.owner_id == user.id))
    if device is None:
        raise HTTPException(404, "Device not found")
    if device.captures:
        raise HTTPException(409, "Device has captures; delete them first")
    db.delete(device)
    db.commit()
    return Response(status_code=204)

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, ConflictError, NotFoundError
from app.core.security import generate_api_key, hash_api_key
from app.models import Device, User


def authenticate_device(db: Session, api_key: str) -> Device:
    device = db.scalar(select(Device).where(Device.api_key_hash == hash_api_key(api_key)))
    if device is None:
        raise AuthError("Invalid API key")
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return device


def create_device(db: Session, owner: User, name: str) -> tuple[Device, str]:
    """Returns the new device and its plain API key; only the key's hash is stored."""
    api_key = generate_api_key()
    device = Device(owner_id=owner.id, name=name, api_key_hash=hash_api_key(api_key))
    db.add(device)
    db.commit()
    db.refresh(device)
    return device, api_key


def list_devices(db: Session, owner: User) -> Sequence[Device]:
    return db.scalars(select(Device).where(Device.owner_id == owner.id).order_by(Device.created_at)).all()


def delete_device(db: Session, owner: User, device_id: uuid.UUID) -> None:
    device = db.scalar(select(Device).where(Device.id == device_id, Device.owner_id == owner.id))
    if device is None:
        raise NotFoundError("Device not found")
    if device.captures:
        raise ConflictError("Device has captures; delete them first")
    db.delete(device)
    db.commit()

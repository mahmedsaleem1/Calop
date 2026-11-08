import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, ConflictError, NotFoundError
from app.core.security import generate_api_key, hash_api_key
from app.models import Device, DeviceApiKey, User
from app.services.event_service import record_event

KEY_PREFIX_LENGTH = 6


def _new_key_row(device_id: uuid.UUID) -> tuple[DeviceApiKey, str]:
    api_key = generate_api_key()
    row = DeviceApiKey(device_id=device_id, key_hash=hash_api_key(api_key), key_prefix=api_key[:KEY_PREFIX_LENGTH])
    return row, api_key


def _live_key(db: Session, device_id: uuid.UUID) -> DeviceApiKey | None:
    return db.scalar(select(DeviceApiKey).where(DeviceApiKey.device_id == device_id, DeviceApiKey.revoked_at.is_(None)))


def authenticate_device(db: Session, api_key: str, firmware_version: str | None = None) -> Device:
    row = db.execute(
        select(DeviceApiKey, Device).join(Device, Device.id == DeviceApiKey.device_id)
        .where(
            DeviceApiKey.key_hash == hash_api_key(api_key),
            DeviceApiKey.revoked_at.is_(None),
            Device.status == "active",
        )
    ).first()
    if row is None:
        raise AuthError("Invalid API key", code="invalid_api_key")
    key, device = row
    now = datetime.now(timezone.utc)
    key.last_used_at = now
    device.last_seen_at = now
    if firmware_version:
        device.firmware_version = firmware_version[:100]
    db.commit()
    return device


def create_device(db: Session, owner: User, name: str) -> tuple[Device, str]:
    """Returns the new device and its plain API key; only the key's hash is stored."""
    if db.scalar(select(Device.id).where(Device.owner_id == owner.id, Device.status == "active")) is not None:
        raise ConflictError("You already have an active device", code="device_exists")
    try:
        device = Device(owner_id=owner.id, name=name, status="active")
        db.add(device)
        db.flush()
        key_row, api_key = _new_key_row(device.id)
        db.add(key_row)
        record_event(db, "user", owner.id, "device.created", "device", device.id, {"user_id": str(owner.id)})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("You already have an active device", code="device_exists")
    db.refresh(device)
    return device, api_key


def list_devices(db: Session, owner: User) -> Sequence[Device]:
    return db.scalars(select(Device).where(Device.owner_id == owner.id).order_by(Device.created_at.desc())).all()


def get_owned_device(db: Session, owner: User, device_id: uuid.UUID) -> Device:
    device = db.scalar(select(Device).where(Device.id == device_id, Device.owner_id == owner.id))
    if device is None:
        raise NotFoundError("Device not found", code="device_not_found")
    return device


def rename_device(db: Session, owner: User, device_id: uuid.UUID, name: str) -> Device:
    device = get_owned_device(db, owner, device_id)
    device.name = name
    record_event(db, "user", owner.id, "device.renamed", "device", device.id, {"user_id": str(owner.id)})
    db.commit()
    return device


def rotate_key(db: Session, owner: User, device_id: uuid.UUID) -> str:
    device = get_owned_device(db, owner, device_id)
    if device.status != "active":
        raise ConflictError("Device is revoked", code="device_revoked")
    live = _live_key(db, device.id)
    if live is not None:
        live.revoked_at = datetime.now(timezone.utc)
        db.flush()  # free the "one live key" index first
    key_row, api_key = _new_key_row(device.id)
    db.add(key_row)
    record_event(db, "user", owner.id, "device.key_rotated", "device", device.id, {"user_id": str(owner.id)})
    db.commit()
    return api_key


def revoke_device(db: Session, owner: User, device_id: uuid.UUID) -> None:
    """Revokes the device and its keys. Its captures stay."""
    device = get_owned_device(db, owner, device_id)
    if device.status == "revoked":
        return
    now = datetime.now(timezone.utc)
    device.status = "revoked"
    device.revoked_at = now
    live = _live_key(db, device.id)
    if live is not None:
        live.revoked_at = now
    record_event(db, "user", owner.id, "device.revoked", "device", device.id, {"user_id": str(owner.id)})
    db.commit()

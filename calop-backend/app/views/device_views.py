import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Device


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DeviceUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    status: str
    firmware_version: str | None = None
    created_at: datetime
    last_seen_at: datetime | None


class DeviceCreated(DeviceOut):
    api_key: str  # shown only once


class ApiKeyOut(BaseModel):
    api_key: str  # shown only once


def build_device_created(device: Device, api_key: str) -> DeviceCreated:
    return DeviceCreated(**DeviceOut.model_validate(device).model_dump(), api_key=api_key)

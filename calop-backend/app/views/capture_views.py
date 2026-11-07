import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CaptureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    device_id: uuid.UUID
    weight_g: float
    image_url: str
    received_at: datetime
    notes: str | None
    food_label: str | None


class CaptureUpdate(BaseModel):
    weight_g: float | None = Field(default=None, ge=-100, le=50000)
    notes: str | None = None
    food_label: str | None = Field(default=None, max_length=255)


class CaptureList(BaseModel):
    items: list[CaptureOut]
    total: int
    limit: int
    offset: int

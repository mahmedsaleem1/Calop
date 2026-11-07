import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignUpIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str | None


class SessionOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
    user: UserOut


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    created_at: datetime
    last_seen_at: datetime | None


class DeviceCreated(DeviceOut):
    api_key: str  # shown only once


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: str
    provider: str | None
    label: str | None
    confidence: float | None
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    notes: str | None
    error: str | None
    completed_at: datetime | None


class CaptureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    device_id: uuid.UUID
    weight_g: float
    image_url: str
    received_at: datetime
    notes: str | None
    food_label: str | None
    analysis: AnalysisOut | None


class CaptureUpdate(BaseModel):
    weight_g: float | None = Field(default=None, ge=-100, le=50000)
    notes: str | None = None
    food_label: str | None = Field(default=None, max_length=255)


class CaptureList(BaseModel):
    items: list[CaptureOut]
    total: int
    limit: int
    offset: int

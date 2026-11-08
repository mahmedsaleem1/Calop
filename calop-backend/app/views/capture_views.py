import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.views.food_views import FoodRef
from app.views.log_views import EntryOut


class CandidateOut(BaseModel):
    code: str
    display_name: str
    confidence: float


class CaptureOut(BaseModel):
    id: uuid.UUID
    source: str
    status: str
    weight_g: float | None
    weight_source: str
    image_status: str
    image_url: str  # always the API image route, so the app never needs to know where the file lives
    captured_at: datetime | None
    received_at: datetime
    candidates: list[CandidateOut]
    not_in_catalog_label: str | None
    selected_food: FoodRef | None
    entry: EntryOut | None


class CaptureList(BaseModel):
    items: list[CaptureOut]
    total: int
    limit: int
    offset: int


class CaptureWeightUpdate(BaseModel):
    weight_g: float = Field(gt=0, le=50000)


class SelectFoodIn(BaseModel):
    food_code: str


class DeviceCaptureStatusOut(BaseModel):
    status: str

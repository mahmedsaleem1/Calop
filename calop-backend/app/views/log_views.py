import uuid
from datetime import date

from pydantic import BaseModel

from app.views.food_views import FoodRef, NutrientAmountOut


class EntryOut(BaseModel):
    id: uuid.UUID
    capture_id: uuid.UUID
    food: FoodRef
    weight_g: float
    weight_source: str
    resolution: str
    local_date: date
    nutrients: list[NutrientAmountOut]
    missing: list[str]


class EntryList(BaseModel):
    items: list[EntryOut]


class EntryFoodUpdate(BaseModel):
    food_code: str

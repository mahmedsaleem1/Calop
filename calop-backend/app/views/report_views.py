from datetime import date

from pydantic import BaseModel

from app.views.log_views import EntryOut
from app.views.me_views import WeightEntryOut


class DayTargetOut(BaseModel):
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbohydrate_g: float
    floor_applied: bool


class NutrientTotalOut(BaseModel):
    code: str
    name: str
    unit: str
    amount: float
    entries_with_data: int  # how many entries had a value for this nutrient
    entries_total: int


class RemainingOut(BaseModel):
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbohydrate_g: float


class DailyReportOut(BaseModel):
    date: date
    target: DayTargetOut | None
    totals: list[NutrientTotalOut]
    remaining: RemainingOut | None
    entries: list[EntryOut]
    estimated_entries: int  # entries whose weight is a user estimate


class DaySummaryOut(BaseModel):
    date: date
    entries: int
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbohydrate_g: float
    target: DayTargetOut | None


class AveragesOut(BaseModel):
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbohydrate_g: float


class WeeklyGoalOut(BaseModel):
    start_weight_kg: float
    target_weight_kg: float
    target_date: date
    latest_weight_kg: float | None


class WeeklyReportOut(BaseModel):
    week_start: date
    week_end: date
    days: list[DaySummaryOut]
    days_logged: int
    averages: AveragesOut  # over the days that have logged entries
    weights: list[WeightEntryOut]
    goal: WeeklyGoalOut | None

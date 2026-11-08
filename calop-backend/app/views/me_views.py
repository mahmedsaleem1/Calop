import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import Goal, NutritionTarget, UserProfile


class ProfileFields(BaseModel):
    date_of_birth: date
    sex: Literal["male", "female"]
    height_cm: float = Field(ge=100, le=250)
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"]
    diet_type: Literal["none", "vegetarian"]
    allergies: list[str] = Field(default_factory=list, max_length=30)
    timezone: str | None = None


class OnboardingIn(ProfileFields):
    weight_kg: float = Field(ge=25, le=350)
    target_weight_kg: float = Field(ge=25, le=350)
    target_date: date


class ProfileUpdate(BaseModel):
    date_of_birth: date | None = None
    sex: Literal["male", "female"] | None = None
    height_cm: float | None = Field(default=None, ge=100, le=250)
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"] | None = None
    diet_type: Literal["none", "vegetarian"] | None = None
    allergies: list[str] | None = Field(default=None, max_length=30)
    timezone: str | None = None


class WeightIn(BaseModel):
    weight_kg: float = Field(ge=25, le=350)


class GoalIn(BaseModel):
    target_weight_kg: float = Field(ge=25, le=350)
    target_date: date


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    date_of_birth: date
    sex: str
    height_cm: float
    activity_level: str
    diet_type: str
    allergies: list[str]
    timezone: str


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    start_weight_kg: float
    target_weight_kg: float
    start_date: date
    target_date: date
    status: str


class TargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    effective_from: datetime
    maintenance_kcal: float
    daily_adjustment_kcal: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbohydrate_g: float
    floor_applied: bool


class WarningOut(BaseModel):
    code: str
    message: str
    suggested_target_date: date | None


class MeOut(BaseModel):
    id: uuid.UUID
    email: str | None
    onboarding_completed: bool
    profile: ProfileOut | None
    current_weight_kg: float | None
    goal: GoalOut | None
    target: TargetOut | None


class OnboardingOut(BaseModel):
    profile: ProfileOut
    goal: GoalOut
    target: TargetOut
    warnings: list[WarningOut]


class ProfileUpdateOut(BaseModel):
    profile: ProfileOut
    target: TargetOut
    warnings: list[WarningOut]


class WeightEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    weight_kg: float
    source: str
    recorded_at: datetime


class WeightRecordedOut(BaseModel):
    entry: WeightEntryOut
    target: TargetOut
    warnings: list[WarningOut]


class GoalSetOut(BaseModel):
    goal: GoalOut
    target: TargetOut
    warnings: list[WarningOut]


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    occurred_at: datetime
    actor_type: str
    action: str
    entity_type: str
    entity_id: str
    data: dict | None


def warnings_out(warnings) -> list[WarningOut]:
    return [WarningOut(code=w.code, message=w.message, suggested_target_date=w.suggested_target_date) for w in warnings]


def build_me(user, profile: UserProfile | None, weight, goal: Goal | None, target: NutritionTarget | None) -> MeOut:
    return MeOut(
        id=user.id, email=user.email, onboarding_completed=user.onboarding_completed_at is not None,
        profile=ProfileOut.model_validate(profile) if profile else None,
        current_weight_kg=float(weight.weight_kg) if weight else None,
        goal=GoalOut.model_validate(goal) if goal else None,
        target=TargetOut.model_validate(target) if target else None,
    )

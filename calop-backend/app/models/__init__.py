"""Importing this package registers every table on Base.metadata (Alembic relies on it)."""
from app.models.capture import Capture, RecognitionCandidate, RecognitionRun
from app.models.device import Device, DeviceApiKey
from app.models.event import Event
from app.models.food import Food, FoodAlias, FoodGroup, FoodNutrient, FoodSearchMiss, FoodSource, Nutrient
from app.models.job import Job
from app.models.log import FoodLogEntry, FoodLogEntryNutrient
from app.models.user import Goal, NutritionTarget, User, UserProfile, WeightEntry

__all__ = [
    "Capture", "RecognitionCandidate", "RecognitionRun", "Device", "DeviceApiKey", "Event",
    "Food", "FoodAlias", "FoodGroup", "FoodNutrient", "FoodSearchMiss", "FoodSource", "Nutrient",
    "Job", "FoodLogEntry", "FoodLogEntryNutrient", "Goal", "NutritionTarget", "User", "UserProfile", "WeightEntry",
]

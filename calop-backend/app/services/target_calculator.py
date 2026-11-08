"""Daily nutrition target maths. Pure functions, no database access."""
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

METHOD = "mifflin_st_jeor_v1"

ACTIVITY_FACTORS = {
    "sedentary": Decimal("1.2"),
    "light": Decimal("1.375"),
    "moderate": Decimal("1.55"),
    "active": Decimal("1.725"),
    "very_active": Decimal("1.9"),
}
KCAL_PER_KG = Decimal(7700)
MAX_DAILY_ADJUSTMENT = Decimal(1100)  # 1 kg per week
CALORIE_FLOORS = {"female": Decimal(1200), "male": Decimal(1500)}
# protein / fat / carbohydrate share of energy
MACRO_SPLITS = {
    "lose": (Decimal("0.30"), Decimal("0.30"), Decimal("0.40")),
    "maintain": (Decimal("0.20"), Decimal("0.30"), Decimal("0.50")),
    "gain": (Decimal("0.25"), Decimal("0.25"), Decimal("0.50")),
}
MAINTAIN_BAND_KG = Decimal("0.5")


class InvalidTargetDate(ValueError):
    pass


@dataclass
class TargetWarning:
    code: str
    message: str
    suggested_target_date: date | None


@dataclass
class TargetResult:
    goal_type: str
    maintenance_kcal: Decimal
    daily_adjustment_kcal: Decimal
    energy_kcal: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbohydrate_g: Decimal
    floor_applied: bool
    warnings: list[TargetWarning] = field(default_factory=list)
    inputs: dict = field(default_factory=dict)


def age_in_years(date_of_birth: date, today: date) -> int:
    years = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return years


def goal_type_for(start_or_current_kg: Decimal, target_kg: Decimal) -> str:
    change = target_kg - start_or_current_kg
    if abs(change) < MAINTAIN_BAND_KG:
        return "maintain"
    return "lose" if change < 0 else "gain"


def _round1(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), ROUND_HALF_UP)


def calculate_target(
    sex: str,
    age: int,
    height_cm: Decimal,
    weight_kg: Decimal,
    activity_level: str,
    target_weight_kg: Decimal,
    target_date: date,
    today: date,
) -> TargetResult:
    height_cm, weight_kg, target_weight_kg = Decimal(height_cm), Decimal(weight_kg), Decimal(target_weight_kg)

    bmr = Decimal(10) * weight_kg + Decimal("6.25") * height_cm - Decimal(5) * age + (5 if sex == "male" else -161)
    factor = ACTIVITY_FACTORS[activity_level]
    maintenance = bmr * factor

    change_kg = target_weight_kg - weight_kg
    goal_type = goal_type_for(weight_kg, target_weight_kg)
    days = (target_date - today).days
    if goal_type != "maintain" and days <= 0:
        raise InvalidTargetDate("target_date must be in the future")

    warnings: list[TargetWarning] = []
    if goal_type == "maintain":
        adjustment = Decimal(0)
    else:
        adjustment = change_kg * KCAL_PER_KG / Decimal(days)
        if abs(adjustment) > MAX_DAILY_ADJUSTMENT:
            adjustment = MAX_DAILY_ADJUSTMENT if adjustment > 0 else -MAX_DAILY_ADJUSTMENT
            suggested = today + timedelta(days=math.ceil(abs(change_kg) * 7))
            warnings.append(TargetWarning(
                "goal_too_fast",
                "This goal needs more than 1 kg of change per week. A slower date is safer.",
                suggested,
            ))

    energy = maintenance + adjustment
    floor = CALORIE_FLOORS[sex]
    floor_applied = False
    if energy < floor:
        energy = floor
        floor_applied = True
        suggested = None
        if goal_type == "lose" and maintenance > floor:
            suggested = today + timedelta(days=math.ceil(abs(change_kg) * KCAL_PER_KG / (maintenance - floor)))
        warnings.append(TargetWarning(
            "calorie_floor",
            f"Your daily target was raised to the minimum of {int(floor)} kcal.",
            suggested,
        ))

    protein_share, fat_share, carb_share = MACRO_SPLITS[goal_type]
    return TargetResult(
        goal_type=goal_type,
        maintenance_kcal=_round1(maintenance),
        daily_adjustment_kcal=_round1(adjustment),
        energy_kcal=_round1(energy),
        protein_g=_round1(energy * protein_share / 4),
        fat_g=_round1(energy * fat_share / 9),
        carbohydrate_g=_round1(energy * carb_share / 4),
        floor_applied=floor_applied,
        warnings=warnings,
        inputs={
            "sex": sex, "age": age, "height_cm": str(height_cm), "weight_kg": str(weight_kg),
            "activity_level": activity_level, "activity_factor": str(factor),
            "target_weight_kg": str(target_weight_kg), "target_date": target_date.isoformat(),
            "today": today.isoformat(), "days": days, "change_kg": str(change_kg), "goal_type": goal_type,
            "bmr": str(_round1(bmr)), "calorie_floor": str(floor),
            "macro_split": [str(protein_share), str(fat_share), str(carb_share)],
        },
    )

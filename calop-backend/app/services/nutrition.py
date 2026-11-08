"""Pure nutrition maths: no database, no network. Amounts come only from the reference table."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.seeds.nutrient_definitions import REPORTED_CODES

_THREE_PLACES = Decimal("0.001")


@dataclass
class NutrientAmount:
    nutrient_id: int
    code: str
    name: str
    unit: str
    amount: Decimal


@dataclass
class NutritionResult:
    amounts: list[NutrientAmount]
    missing: list[str]  # reported nutrients the food has no value for


def compute_nutrition(food: Any, weight_g: Decimal | float | int | str) -> NutritionResult:
    """amount = amount_per_100g × weight_g ÷ 100, rounded to 3 places. Never invents a value:
    a nutrient the source doesn't report is listed in `missing`, not estimated."""
    weight = Decimal(str(weight_g))
    rows = sorted(food.nutrient_rows, key=lambda row: row.nutrient.sort_order)
    amounts = [
        NutrientAmount(
            nutrient_id=row.nutrient_id,
            code=row.nutrient.code,
            name=row.nutrient.name,
            unit=row.nutrient.unit,
            amount=(Decimal(str(row.amount_per_100g)) * weight / Decimal(100)).quantize(_THREE_PLACES, ROUND_HALF_UP),
        )
        for row in rows
    ]
    present = {item.code for item in amounts}
    missing = sorted(REPORTED_CODES - present)
    return NutritionResult(amounts=amounts, missing=missing)

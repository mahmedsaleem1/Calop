from decimal import Decimal

from pydantic import BaseModel

from app.models import Food
from app.services.food_service import SearchResult
from app.services.nutrition import NutritionResult


class FoodHitOut(BaseModel):
    code: str
    display_name: str
    group: str
    preparation_state: str
    score: float


class FoodSearchOut(BaseModel):
    match_type: str
    items: list[FoodHitOut]


class FoodGroupOut(BaseModel):
    code: str
    name: str


class FoodNutrientPer100g(BaseModel):
    code: str
    name: str
    unit: str
    amount_per_100g: float


class FoodAliasOut(BaseModel):
    alias: str
    kind: str
    is_preferred: bool


class FoodDetailOut(BaseModel):
    code: str
    display_name: str
    source_name: str
    source_local_name: str | None
    scientific_name: str | None
    group: str
    kind: str
    preparation_state: str
    quality_flags: list[str]
    ingredients_text: str | None
    preparation_method: str | None
    aliases: list[FoodAliasOut]
    nutrients: list[FoodNutrientPer100g]


class FoodRef(BaseModel):
    code: str
    display_name: str


class NutrientAmountOut(BaseModel):
    code: str
    name: str
    unit: str
    amount: float


class FoodNutritionOut(BaseModel):
    food: FoodRef
    weight_g: float
    nutrients: list[NutrientAmountOut]
    missing: list[str]


def build_search_out(result: SearchResult) -> FoodSearchOut:
    return FoodSearchOut(
        match_type=result.match_type,
        items=[FoodHitOut(**vars(hit)) for hit in result.items],
    )


def build_food_detail(food: Food) -> FoodDetailOut:
    rows = sorted(food.nutrient_rows, key=lambda row: row.nutrient.sort_order)
    return FoodDetailOut(
        code=food.code, display_name=food.display_name, source_name=food.source_name,
        source_local_name=food.source_local_name, scientific_name=food.scientific_name, group=food.group.code,
        kind=food.kind, preparation_state=food.preparation_state, quality_flags=list(food.quality_flags or []),
        ingredients_text=food.ingredients_text, preparation_method=food.preparation_method,
        aliases=[
            FoodAliasOut(alias=a.alias, kind=a.kind, is_preferred=a.is_preferred)
            for a in sorted(food.aliases, key=lambda a: (not a.is_preferred, a.alias))
        ],
        nutrients=[
            FoodNutrientPer100g(
                code=r.nutrient.code, name=r.nutrient.name, unit=r.nutrient.unit, amount_per_100g=r.amount_per_100g
            )
            for r in rows
        ],
    )


def build_nutrition_out(food: Food, weight_g: Decimal | float, result: NutritionResult) -> FoodNutritionOut:
    return FoodNutritionOut(
        food=FoodRef(code=food.code, display_name=food.display_name),
        weight_g=float(weight_g),
        nutrients=[
            NutrientAmountOut(code=a.code, name=a.name, unit=a.unit, amount=a.amount) for a in result.amounts
        ],
        missing=result.missing,
    )

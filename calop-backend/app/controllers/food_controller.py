from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.dependencies import get_current_user
from app.core.database import get_db
from app.core.exceptions import UnprocessableInputError
from app.models import User
from app.services import food_service
from app.views.food_views import (
    FoodDetailOut, FoodGroupOut, FoodNutritionOut, FoodSearchOut, build_food_detail, build_nutrition_out,
    build_search_out,
)

router = APIRouter(prefix="/api/v1", tags=["foods"])


@router.get("/foods", response_model=FoodSearchOut)
def search_foods(
    q: str | None = None,
    group: str | None = None,
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Search the food table by name (English, Urdu, common spellings). Needs `q` or `group`."""
    if not (q and q.strip()) and not group:
        raise UnprocessableInputError("Provide q or group", code="query_required")
    return build_search_out(food_service.search_foods(db, q, group, limit, user_id=current_user.id))


@router.get("/food-groups", response_model=list[FoodGroupOut])
def list_food_groups(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return food_service.list_groups(db)


@router.get("/foods/{code}", response_model=FoodDetailOut)
def get_food(code: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_food_detail(food_service.get_food(db, code))


@router.get("/foods/{code}/nutrition", response_model=FoodNutritionOut)
def get_food_nutrition(
    code: str,
    weight_g: float = Query(..., gt=0, le=50000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Nutrients for a weight of this food: amount per 100 g × weight ÷ 100."""
    food = food_service.get_food(db, code)
    return build_nutrition_out(food, weight_g, food_service.compute_nutrition(food, weight_g))

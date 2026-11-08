import uuid
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import NotFoundError
from app.models import Food, FoodAlias, FoodGroup, FoodSearchMiss
from app.services.food_text import normalize_text
from app.services.nutrition import compute_nutrition  # noqa: F401  (re-exported)

FUZZY_THRESHOLD = 0.3
ALIAS_KIND_ORDER = {"common": 0, "spelling": 1, "local": 2, "source": 3}
MAX_CATALOG_ALIASES = 5


@dataclass
class FoodHit:
    code: str
    display_name: str
    group: str
    preparation_state: str
    score: float


@dataclass
class SearchResult:
    match_type: str  # exact | fuzzy | group | none
    items: list[FoodHit]


def _hit_columns():
    return (Food.id, Food.code, Food.display_name, FoodGroup.code.label("group_code"), Food.preparation_state)


def search_foods(
    db: Session, query: str | None, group_code: str | None = None, limit: int = 10, user_id: uuid.UUID | None = None
) -> SearchResult:
    normalized = normalize_text(query or "")

    if not normalized:
        if not group_code:
            return SearchResult("none", [])
        rows = db.execute(
            select(*_hit_columns()).join(FoodGroup, Food.group_id == FoodGroup.id)
            .where(Food.is_searchable, FoodGroup.code == group_code)
            .order_by(Food.display_name).limit(limit)
        ).all()
        return SearchResult("group", [FoodHit(r.code, r.display_name, r.group_code, r.preparation_state, 1.0) for r in rows])

    base = (
        select(*_hit_columns()).join(FoodGroup, Food.group_id == FoodGroup.id)
        .join(FoodAlias, FoodAlias.food_id == Food.id).where(Food.is_searchable)
    )
    if group_code:
        base = base.where(FoodGroup.code == group_code)

    exact_rows = db.execute(
        base.add_columns(FoodAlias.is_preferred)
        .where(FoodAlias.normalized_alias == normalized)
        .order_by(FoodAlias.is_preferred.desc(), Food.display_name)
    ).all()
    if exact_rows:
        seen: set[str] = set()
        hits = []
        for r in exact_rows:
            if r.code not in seen:
                seen.add(r.code)
                hits.append(FoodHit(r.code, r.display_name, r.group_code, r.preparation_state, 1.0))
        return SearchResult("exact", hits[:limit])

    score = func.max(func.similarity(FoodAlias.normalized_alias, normalized)).label("score")
    fuzzy_rows = db.execute(
        base.add_columns(score)
        .group_by(Food.id, Food.code, Food.display_name, FoodGroup.code, Food.preparation_state)
        .having(func.max(func.similarity(FoodAlias.normalized_alias, normalized)) > FUZZY_THRESHOLD)
        .order_by(score.desc(), Food.display_name).limit(limit)
    ).all()
    if fuzzy_rows:
        return SearchResult(
            "fuzzy",
            [FoodHit(r.code, r.display_name, r.group_code, r.preparation_state, round(float(r.score), 3)) for r in fuzzy_rows],
        )

    db.add(FoodSearchMiss(user_id=user_id, query=(query or "").strip(), normalized_query=normalized, context="app_search"))
    db.commit()
    return SearchResult("none", [])


def get_food(db: Session, code: str) -> Food:
    food = db.scalar(select(Food).where(Food.code == code))
    if food is None:
        raise NotFoundError("Food not found", code="food_not_found")
    return food


def list_groups(db: Session) -> list[FoodGroup]:
    return list(db.scalars(select(FoodGroup).order_by(FoodGroup.sort_order)))


# ---- catalog shown to the AI ----

@dataclass(frozen=True)
class CatalogEntry:
    food_id: int
    code: str
    display_name: str
    preparation_state: str
    aliases: tuple[str, ...]


@lru_cache
def matchable_catalog() -> tuple[CatalogEntry, ...]:
    """The foods the AI may choose, cached in memory. Restart the server after reseeding."""
    with SessionLocal() as db:
        foods = db.scalars(select(Food).where(Food.is_matchable).order_by(Food.id)).all()
        entries = []
        for food in foods:
            display = normalize_text(food.display_name)
            ranked = sorted(food.aliases, key=lambda a: (not a.is_preferred, ALIAS_KIND_ORDER.get(a.kind, 9), a.alias))
            names: list[str] = []
            seen = {display}
            for alias in ranked:
                if alias.normalized_alias not in seen:
                    seen.add(alias.normalized_alias)
                    names.append(alias.alias)
                if len(names) == MAX_CATALOG_ALIASES:
                    break
            entries.append(CatalogEntry(food.id, food.code, food.display_name, food.preparation_state, tuple(names)))
        return tuple(entries)


def catalog_by_code() -> dict[str, CatalogEntry]:
    return {entry.code: entry for entry in matchable_catalog()}


def catalog_text() -> str:
    return "\n".join(
        f"{e.code} | {e.display_name} | {e.preparation_state} | {', '.join(e.aliases)}" for e in matchable_catalog()
    )

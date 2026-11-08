"""Seeds the food reference tables from data/reference/. Idempotent: running it twice gives the same result.

    python -m app.seeds.reference
"""
import csv
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.seeds.nutrient_definitions import NUTRIENTS
from app.services.food_text import normalize_text

REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "reference"

SOURCE = {
    "code": "fct_pk_2001",
    "title": "Food Composition Table for Pakistan (Revised 2001)",
    "publisher": (
        "Dept. of Agricultural Chemistry, NWFP Agricultural University Peshawar; UNICEF; "
        "Ministry of Planning & Development"
    ),
    "year": 2001,
    "url": "https://www.fao.org/infoods/infoods/tables-and-databases/pakistan/en/",
}

KINDS = {"ingredient", "dish", "recipe"}
PREPARATION_STATES = {"raw", "cooked", "processed", "unknown"}
ALIAS_KINDS = {"source", "local", "common", "spelling"}
ENERGY_MISMATCH_TOLERANCE = Decimal("0.20")
MAX_PROXIMATE_GRAMS = Decimal(105)


class ReferenceDataError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("Reference data is invalid:\n  - " + "\n  - ".join(problems))
        self.problems = problems


@dataclass
class ReferenceData:
    foods: list[dict]
    food_nutrients: list[dict]
    groups: list[dict]
    curation: dict[str, dict]
    manual_aliases: list[dict]


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _to_bool(value: str) -> bool | None:
    return {"true": True, "false": False}.get(value.strip().lower())


def load_reference(directory: Path = REFERENCE_DIR) -> ReferenceData:
    extracted = directory / "extracted"
    return ReferenceData(
        foods=_read_csv(extracted / "foods.csv"),
        food_nutrients=_read_csv(extracted / "food_nutrients.csv"),
        groups=_read_csv(extracted / "food_groups.csv"),
        curation={row["code"]: row for row in _read_csv(directory / "curation.csv")},
        manual_aliases=_read_csv(directory / "aliases.csv"),
    )


def validate(reference: ReferenceData) -> list[str]:
    problems: list[str] = []
    food_codes = {food["code"] for food in reference.foods}
    nutrient_codes = {n.code for n in NUTRIENTS}
    group_codes = {group["code"] for group in reference.groups}

    for code in sorted(food_codes - reference.curation.keys()):
        problems.append(f"food {code} is missing from curation.csv")
    for code in sorted(reference.curation.keys() - food_codes):
        problems.append(f"curation.csv lists unknown food {code}")
    for code, row in reference.curation.items():
        if row["preparation_state"] not in PREPARATION_STATES:
            problems.append(f"{code}: invalid preparation_state {row['preparation_state']!r}")
        for column in ("is_matchable", "is_searchable"):
            if _to_bool(row[column]) is None:
                problems.append(f"{code}: invalid {column} {row[column]!r}")
        if not row["display_name"].strip():
            problems.append(f"{code}: empty display_name")
    for food in reference.foods:
        if food["kind"] not in KINDS:
            problems.append(f"{food['code']}: invalid kind {food['kind']!r}")
        if food["group_code"] not in group_codes:
            problems.append(f"{food['code']}: unknown group {food['group_code']!r}")

    for alias in reference.manual_aliases:
        if alias["food_code"] not in food_codes:
            problems.append(f"alias {alias['alias']!r} points to unknown food {alias['food_code']}")
        if alias["kind"] not in ALIAS_KINDS:
            problems.append(f"alias {alias['alias']!r}: invalid kind {alias['kind']!r}")
        if _to_bool(alias["is_preferred"]) is None:
            problems.append(f"alias {alias['alias']!r}: invalid is_preferred {alias['is_preferred']!r}")
        if not normalize_text(alias["alias"]):
            problems.append(f"alias {alias['alias']!r} is empty after normalization")

    preferred_owners: dict[str, set[str]] = defaultdict(set)
    for alias in reference.manual_aliases:
        if _to_bool(alias["is_preferred"]):
            preferred_owners[normalize_text(alias["alias"])].add(alias["food_code"])
    for normalized, owners in sorted(preferred_owners.items()):
        if len(owners) > 1:
            problems.append(f"alias {normalized!r} is preferred for more than one food: {sorted(owners)}")

    per_food: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for row in reference.food_nutrients:
        if row["food_code"] not in food_codes:
            problems.append(f"nutrient value for unknown food {row['food_code']}")
            continue
        if row["nutrient_code"] not in nutrient_codes:
            problems.append(f"{row['food_code']}: unknown nutrient {row['nutrient_code']}")
            continue
        amount = Decimal(row["amount_per_100g"])
        if amount < 0:
            problems.append(f"{row['food_code']}: negative {row['nutrient_code']} ({amount})")
        per_food[row["food_code"]][row["nutrient_code"]] = amount
    for code, values in per_food.items():
        total = sum(values.get(k, Decimal(0)) for k in ("protein_g", "fat_g", "carbohydrate_g", "fibre_g"))
        if total > MAX_PROXIMATE_GRAMS:
            problems.append(f"{code}: protein + fat + carbs + fibre = {total} g per 100 g (over {MAX_PROXIMATE_GRAMS})")
    return problems


def quality_flags(values: dict[str, Decimal]) -> list[str]:
    """Flags computed during seeding. Values are always imported exactly as written."""
    needed = ("energy_kcal", "protein_g", "fat_g", "carbohydrate_g")
    if all(key in values for key in needed) and values["energy_kcal"] > 0:
        computed = 4 * values["protein_g"] + 9 * values["fat_g"] + 4 * values["carbohydrate_g"]
        if abs(computed - values["energy_kcal"]) / values["energy_kcal"] > ENERGY_MISMATCH_TOLERANCE:
            return ["energy_mismatch"]
    return []


def build_aliases(reference: ReferenceData) -> list[dict]:
    """Automatic aliases from the names, plus the hand-written ones, which override."""
    foods = {food["code"]: food for food in reference.foods}
    searchable = {code: _to_bool(row["is_searchable"]) for code, row in reference.curation.items()}

    aliases: dict[tuple[str, str], dict] = {}
    for code, food in foods.items():
        curation = reference.curation[code]
        candidates = [
            ("source", food["source_name"]),
            ("local", food["source_local_name"]),
            ("common", curation["display_name"]),
        ]
        for kind, text in candidates:
            normalized = normalize_text(text or "")
            if normalized and (code, normalized) not in aliases:
                aliases[(code, normalized)] = {
                    "food_code": code, "alias": text.strip(), "normalized_alias": normalized,
                    "kind": kind, "is_preferred": False, "manual": False,
                }
    for row in reference.manual_aliases:
        normalized = normalize_text(row["alias"])
        aliases[(row["food_code"], normalized)] = {
            "food_code": row["food_code"], "alias": row["alias"].strip(), "normalized_alias": normalized,
            "kind": row["kind"], "is_preferred": bool(_to_bool(row["is_preferred"])), "manual": True,
        }

    owners: dict[str, set[str]] = defaultdict(set)
    manual_preferred: set[str] = set()
    for (code, normalized), alias in aliases.items():
        if searchable.get(code):
            owners[normalized].add(code)
        if alias["manual"] and alias["is_preferred"]:
            manual_preferred.add(normalized)
    for (code, normalized), alias in aliases.items():
        if not alias["manual"]:
            alias["is_preferred"] = (
                bool(searchable.get(code)) and len(owners[normalized]) == 1 and normalized not in manual_preferred
            )
    return list(aliases.values())


def seed(db) -> dict[str, int]:
    from sqlalchemy import delete, select

    from app.models import Food, FoodAlias, FoodGroup, FoodNutrient, FoodSource, Nutrient

    reference = load_reference()
    problems = validate(reference)
    if problems:
        raise ReferenceDataError(problems)

    # source
    source = db.scalar(select(FoodSource).where(FoodSource.code == SOURCE["code"]))
    if source is None:
        source = FoodSource(**SOURCE)
        db.add(source)
    else:
        for key, value in SOURCE.items():
            setattr(source, key, value)

    # groups and nutrients, keyed by code
    groups = {g.code: g for g in db.scalars(select(FoodGroup))}
    for row in reference.groups:
        group = groups.get(row["code"]) or FoodGroup(code=row["code"])
        group.name, group.sort_order = row["name"], int(row["sort_order"])
        db.add(group)
        groups[row["code"]] = group
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    for order, definition in enumerate(NUTRIENTS, start=1):
        nutrient = nutrients.get(definition.code) or Nutrient(code=definition.code)
        nutrient.name, nutrient.unit = definition.name, definition.unit
        nutrient.sort_order, nutrient.is_reported = order, definition.is_reported
        db.add(nutrient)
        nutrients[definition.code] = nutrient
    db.flush()

    # foods
    values_by_food: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for row in reference.food_nutrients:
        values_by_food[row["food_code"]][row["nutrient_code"]] = Decimal(row["amount_per_100g"])

    existing = {f.code: f for f in db.scalars(select(Food))}
    for row in reference.foods:
        curation = reference.curation[row["code"]]
        food = existing.get(row["code"]) or Food(code=row["code"])
        food.source_id = source.id
        food.source_ref = row["source_ref"]
        food.group_id = groups[row["group_code"]].id
        food.source_name = row["source_name"]
        food.source_local_name = row["source_local_name"] or None
        food.display_name = curation["display_name"].strip()
        food.scientific_name = row["scientific_name"] or None
        food.kind = row["kind"]
        food.preparation_state = curation["preparation_state"]
        food.is_matchable = bool(_to_bool(curation["is_matchable"]))
        food.is_searchable = bool(_to_bool(curation["is_searchable"]))
        food.quality_flags = quality_flags(values_by_food[row["code"]])
        food.ingredients_text = row["ingredients_text"] or None
        food.preparation_method = row["preparation_method"] or None
        db.add(food)
        existing[row["code"]] = food
    db.flush()

    # nutrient rows and aliases: delete and reinsert (removing all aliases first keeps the partial unique index happy)
    food_ids = [food.id for food in existing.values()]
    db.execute(delete(FoodNutrient).where(FoodNutrient.food_id.in_(food_ids)))
    db.execute(delete(FoodAlias).where(FoodAlias.food_id.in_(food_ids)))
    db.expire_all()
    for code, values in values_by_food.items():
        for nutrient_code, amount in values.items():
            db.add(FoodNutrient(food_id=existing[code].id, nutrient_id=nutrients[nutrient_code].id, amount_per_100g=amount))
    aliases = build_aliases(reference)
    for alias in aliases:
        db.add(FoodAlias(
            food_id=existing[alias["food_code"]].id, alias=alias["alias"], normalized_alias=alias["normalized_alias"],
            kind=alias["kind"], is_preferred=alias["is_preferred"],
        ))
    db.commit()
    return {
        "foods": len(reference.foods), "groups": len(reference.groups), "nutrients": len(NUTRIENTS),
        "nutrient_values": len(reference.food_nutrients), "aliases": len(aliases),
    }


def main() -> None:
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        counts = seed(db)
    print("Seeded: " + ", ".join(f"{count} {name}" for name, count in counts.items()))


if __name__ == "__main__":
    main()

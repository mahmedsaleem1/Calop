"""Reads Food_Composition_Table_Pakistan.xlsx and writes CSV files to data/reference/extracted/.
Never changes values. The output is generated: nobody edits it by hand.

Run from calop-backend/:   python scripts/extract_reference_data.py
"""
import csv
import sys
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.seeds.nutrient_definitions import HEADER_TO_NUTRIENT, NUTRIENTS  # noqa: E402

SOURCE_FILE = ROOT / "data" / "reference" / "source" / "Food_Composition_Table_Pakistan.xlsx"
OUTPUT_DIR = ROOT / "data" / "reference" / "extracted"

# sheet name -> (group code, code prefix, kind)
SHEETS = {
    "Cereal": ("cereal", "MAIN", "ingredient"),
    "Legumes": ("legumes", "MAIN", "ingredient"),
    "Vegetables": ("vegetables", "MAIN", "ingredient"),
    "Roots and Tubers": ("roots_tubers", "MAIN", "ingredient"),
    "Spices": ("spices", "MAIN", "ingredient"),
    "Fruits": ("fruits", "MAIN", "ingredient"),
    "Nuts and Dry Fruits": ("nuts_dry_fruits", "MAIN", "ingredient"),
    "Dairy": ("dairy", "MAIN", "ingredient"),
    "Meat": ("meat", "MAIN", "ingredient"),
    "Fish": ("fish", "MAIN", "ingredient"),
    "Eggs": ("eggs", "MAIN", "ingredient"),
    "Fats and Oil": ("fats_oils", "MAIN", "ingredient"),
    "Sugars and Beverages": ("sugars_beverages", "MAIN", "ingredient"),
    "Traditional Foods": ("traditional_dishes", "TRAD", "dish"),
    "Weaning Foods": ("weaning_foods", "WEAN", "recipe"),
}

TEXT_HEADERS = {
    "Sr. No.": "source_ref",
    "No.": "source_ref",
    "Food (English)": "source_name",
    "Dish": "source_name",
    "Food / Recipe": "source_name",
    "Food (Urdu)": "source_local_name",
    "Scientific Name": "scientific_name",
    "Ingredients and Amounts": "ingredients_text",
    "Method of Preparation": "preparation_method",
}
IGNORED_HEADERS = {"Type", "Appendix Ref."}
REFERENCE_WEIGHT_HEADER = "Reference Weight (gm)"

EXPECTED_FOODS, EXPECTED_MAIN, EXPECTED_TRAD, EXPECTED_WEAN = 224, 198, 17, 9
EXPECTED_GROUPS, EXPECTED_NUTRIENTS = 15, 19


class ExtractionError(Exception):
    pass


@dataclass
class Extracted:
    foods: list[dict]
    food_nutrients: list[dict]
    groups: list[dict]


def _integer_or_none(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def parse_number(value, where: str) -> Decimal | None:
    """None for an empty cell or '-'; a Decimal rounded to 3 places for a number; anything else is an error."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in ("", "-"):
            return None
        raise ExtractionError(f"{where}: cannot read {value!r} as a number")
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ExtractionError(f"{where}: cannot read {value!r} as a number")
    return Decimal(str(value)).quantize(Decimal("0.001"), ROUND_HALF_UP)


def _clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_workbook(workbook) -> Extracted:
    unknown_sheets = [name for name in workbook.sheetnames if name not in SHEETS]
    missing_sheets = [name for name in SHEETS if name not in workbook.sheetnames]
    if unknown_sheets or missing_sheets:
        raise ExtractionError(f"Unexpected sheets {unknown_sheets}, missing sheets {missing_sheets}")

    foods, food_nutrients, groups = [], [], []
    seen_codes: set[str] = set()

    for sort_order, sheet_name in enumerate(SHEETS, start=1):
        group_code, prefix, kind = SHEETS[sheet_name]
        groups.append({"code": group_code, "name": sheet_name, "sort_order": sort_order})
        rows = list(workbook[sheet_name].iter_rows(values_only=True))
        if not rows:
            raise ExtractionError(f"{sheet_name}: sheet is empty")
        headers = [(_clean_text(cell) or "") for cell in rows[0]]
        for header in headers:
            known = (
                header in TEXT_HEADERS or header in IGNORED_HEADERS or header in HEADER_TO_NUTRIENT
                or header == REFERENCE_WEIGHT_HEADER or header == ""
            )
            if not known:
                raise ExtractionError(f"{sheet_name}: unknown header {header!r}")

        for row_number, row in enumerate(rows[1:], start=2):
            ref = _integer_or_none(row[0]) if row else None
            if ref is None:  # section notes, footnotes, blank rows
                continue
            where = f"{sheet_name} row {row_number}"
            food = {
                "code": f"{prefix}-{ref}", "source_ref": str(ref), "group_code": group_code, "kind": kind,
                "source_name": None, "source_local_name": None, "scientific_name": None,
                "ingredients_text": None, "preparation_method": None,
            }
            nutrient_values: dict[str, Decimal] = {}
            for header, cell in zip(headers, row):
                if header in TEXT_HEADERS and TEXT_HEADERS[header] != "source_ref":
                    food[TEXT_HEADERS[header]] = _clean_text(cell)
                elif header in HEADER_TO_NUTRIENT:
                    value = parse_number(cell, f"{where}, {header}")
                    if value is not None:
                        nutrient_values[HEADER_TO_NUTRIENT[header]] = value
                elif header == REFERENCE_WEIGHT_HEADER:
                    weight = parse_number(cell, f"{where}, {header}")
                    if weight != Decimal("100.000"):
                        raise ExtractionError(f"{where}: reference weight is {cell!r}, expected 100")
            if not food["source_name"]:
                raise ExtractionError(f"{where}: food has no name")
            if food["code"] in seen_codes:
                raise ExtractionError(f"{where}: duplicate food code {food['code']}")
            seen_codes.add(food["code"])
            foods.append(food)
            for nutrient_code, amount in nutrient_values.items():
                food_nutrients.append(
                    {"food_code": food["code"], "nutrient_code": nutrient_code, "amount_per_100g": amount}
                )

    return Extracted(foods=foods, food_nutrients=food_nutrients, groups=groups)


def check_expected_counts(extracted: Extracted) -> None:
    problems = []
    codes = [food["code"] for food in extracted.foods]
    main = sorted(int(c.split("-")[1]) for c in codes if c.startswith("MAIN-"))
    trad = [c for c in codes if c.startswith("TRAD-")]
    wean = [c for c in codes if c.startswith("WEAN-")]
    if len(codes) != EXPECTED_FOODS:
        problems.append(f"expected {EXPECTED_FOODS} foods, found {len(codes)}")
    if main != list(range(1, EXPECTED_MAIN + 1)):
        problems.append(f"MAIN foods must be exactly 1..{EXPECTED_MAIN} with no gaps, found {len(main)}")
    if len(trad) != EXPECTED_TRAD:
        problems.append(f"expected {EXPECTED_TRAD} TRAD foods, found {len(trad)}")
    if len(wean) != EXPECTED_WEAN:
        problems.append(f"expected {EXPECTED_WEAN} WEAN foods, found {len(wean)}")
    if len(extracted.groups) != EXPECTED_GROUPS:
        problems.append(f"expected {EXPECTED_GROUPS} groups, found {len(extracted.groups)}")
    used_nutrients = {row["nutrient_code"] for row in extracted.food_nutrients}
    if len(used_nutrients) != EXPECTED_NUTRIENTS or len(NUTRIENTS) != EXPECTED_NUTRIENTS:
        problems.append(f"expected {EXPECTED_NUTRIENTS} nutrients, found {len(used_nutrients)}")
    if problems:
        raise ExtractionError("; ".join(problems))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(extracted: Extracted, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "foods.csv",
        ["code", "source_ref", "group_code", "kind", "source_name", "source_local_name", "scientific_name",
         "ingredients_text", "preparation_method"],
        extracted.foods,
    )
    _write_csv(
        output_dir / "food_nutrients.csv", ["food_code", "nutrient_code", "amount_per_100g"], extracted.food_nutrients
    )
    _write_csv(output_dir / "food_groups.csv", ["code", "name", "sort_order"], extracted.groups)


def main() -> None:
    import openpyxl

    workbook = openpyxl.load_workbook(SOURCE_FILE, data_only=True)
    extracted = parse_workbook(workbook)
    check_expected_counts(extracted)
    write_outputs(extracted, OUTPUT_DIR)
    print(
        f"Extracted {len(extracted.foods)} foods, {len(extracted.groups)} groups, "
        f"{len(extracted.food_nutrients)} nutrient values -> {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    try:
        main()
    except ExtractionError as error:
        sys.exit(f"Extraction failed: {error}")

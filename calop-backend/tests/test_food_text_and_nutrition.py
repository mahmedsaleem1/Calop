from decimal import Decimal
from types import SimpleNamespace

from app.services.food_text import normalize_text
from app.services.nutrition import compute_nutrition


def test_normalize_drops_accents_case_and_punctuation():
    assert normalize_text("  Café-Au_Lait!! ") == "cafe au lait"
    assert normalize_text("Chapati (Roti)") == "chapati roti"
    assert normalize_text("β-Carotene") == "carotene"
    assert normalize_text("A   B\tC") == "a b c"
    assert normalize_text("!!!") == ""


def _food(rows):
    return SimpleNamespace(nutrient_rows=[
        SimpleNamespace(
            nutrient_id=i, amount_per_100g=Decimal(amount),
            nutrient=SimpleNamespace(code=code, name=code, unit="g", sort_order=i),
        )
        for i, (code, amount) in enumerate(rows, start=1)
    ])


def test_compute_nutrition_scales_per_100g():
    food = _food([("energy_kcal", "259"), ("protein_g", "8.8")])
    result = compute_nutrition(food, 50)
    amounts = {a.code: a.amount for a in result.amounts}
    assert amounts == {"energy_kcal": Decimal("129.500"), "protein_g": Decimal("4.400")}


def test_compute_nutrition_rounds_to_three_places():
    result = compute_nutrition(_food([("energy_kcal", "33.333")]), Decimal("33.3"))
    assert result.amounts[0].amount == Decimal("11.100")  # 33.333 * 33.3 / 100 = 11.0999...


def test_missing_lists_reported_nutrients_the_food_lacks():
    result = compute_nutrition(_food([("energy_kcal", "100"), ("moisture_g", "10")]), 100)
    assert "zinc_mg" in result.missing
    assert "energy_kcal" not in result.missing
    assert "moisture_g" not in result.missing  # not a reported nutrient
    assert [a.code for a in result.amounts] == ["energy_kcal", "moisture_g"]  # nothing invented

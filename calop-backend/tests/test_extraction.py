from decimal import Decimal

import openpyxl
import pytest

import extract_reference_data as extract


def workbook(sheets):
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name in extract.SHEETS:
        sheet = book.create_sheet(name)
        for row in sheets.get(name, [["Sr. No.", "Food (English)", "Reference Weight (gm)"]]):
            sheet.append(row)
    return book


CEREAL_HEADER = ["Sr. No.", "Food (English)", "Food (Urdu)", "Food Energy (kcal)", "Protein (g)", "Zinc (mg)",
                 "Reference Weight (gm)"]


def parse(rows):
    return extract.parse_workbook(workbook({"Cereal": [CEREAL_HEADER, *rows]}))


def test_dash_blank_and_float_values():
    result = parse([[1, " Barley ", None, 339, "-", "", 100]])
    food = result.foods[0]
    assert food["code"] == "MAIN-1" and food["source_name"] == "Barley" and food["source_local_name"] is None
    values = {r["nutrient_code"]: r["amount_per_100g"] for r in result.food_nutrients}
    assert values == {"energy_kcal": Decimal("339.000")}  # '-' and blank mean "not reported": no row


def test_float_noise_is_rounded_to_three_places():
    result = parse([[1, "Rice", None, 72.599999999999994, 7.12345, 1, 100]])
    values = {r["nutrient_code"]: r["amount_per_100g"] for r in result.food_nutrients}
    assert values["energy_kcal"] == Decimal("72.600")
    assert values["protein_g"] == Decimal("7.123")
    assert str(values["energy_kcal"]) == "72.600"


def test_rows_without_an_integer_first_cell_are_skipped():
    result = parse([["Note: values are per 100 g", None, None, None, None, None, None], [None] * 7,
                    [2, "Maize", None, 350, 9, 2, 100]])
    assert [f["code"] for f in result.foods] == ["MAIN-2"]


def test_text_in_a_number_cell_fails():
    with pytest.raises(extract.ExtractionError, match="cannot read"):
        parse([[1, "Rice", None, "about 340", 7, 1, 100]])


def test_unknown_header_fails():
    header = CEREAL_HEADER + ["Mystery (mg)"]
    with pytest.raises(extract.ExtractionError, match="unknown header"):
        extract.parse_workbook(workbook({"Cereal": [header, [1, "Rice", None, 1, 1, 1, 100, 5]]}))


def test_reference_weight_must_be_100():
    with pytest.raises(extract.ExtractionError, match="reference weight"):
        parse([[1, "Rice", None, 340, 7, 1, 50]])


def test_expected_counts_fail_on_a_tiny_workbook():
    with pytest.raises(extract.ExtractionError):
        extract.check_expected_counts(parse([[1, "Rice", None, 340, 7, 1, 100]]))


def test_the_real_workbook_matches_the_expected_counts():
    book = openpyxl.load_workbook(extract.SOURCE_FILE, data_only=True)
    result = extract.parse_workbook(book)
    extract.check_expected_counts(result)  # 224 foods, 15 groups, 19 nutrients
    codes = {f["code"] for f in result.foods}
    assert {"MAIN-19", "TRAD-13", "WEAN-9"} <= codes
    trad13 = {r["nutrient_code"] for r in result.food_nutrients if r["food_code"] == "TRAD-13"}
    assert "zinc_mg" not in trad13

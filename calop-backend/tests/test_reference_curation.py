from collections import Counter
from decimal import Decimal

import pytest

from app.seeds import reference as ref


@pytest.fixture(scope="module")
def data():
    return ref.load_reference()


def test_the_committed_reference_data_is_valid(data):
    assert ref.validate(data) == []


def test_every_food_is_curated_exactly_once(data):
    assert {f["code"] for f in data.foods} == set(data.curation)
    assert len(data.foods) == 224


def test_curation_rules_from_the_guide(data):
    cur = data.curation
    assert cur["MAIN-19"]["display_name"] == "Chapati" and cur["MAIN-19"]["is_matchable"] == "true"
    assert cur["MAIN-91"]["is_matchable"] == "false" and cur["TRAD-1"]["is_matchable"] == "false"
    assert cur["TRAD-1"]["is_searchable"] == "false" and cur["MAIN-136"]["is_searchable"] == "false"
    assert cur["WEAN-6"]["display_name"] == "Supplementary Food Mix 1"
    assert cur["WEAN-6"]["is_matchable"] == "false" and cur["WEAN-6"]["is_searchable"] == "false"
    assert cur["MAIN-9"]["preparation_state"] == "cooked" and cur["MAIN-24"]["preparation_state"] == "raw"
    assert cur["MAIN-87"]["preparation_state"] == "processed" and cur["TRAD-13"]["preparation_state"] == "cooked"
    assert cur["MAIN-74"]["is_matchable"] == "false"  # spices
    assert cur["MAIN-175"]["is_matchable"] == "false"  # fats and oils


def test_roti_has_one_preferred_alias_pointing_at_chapati(data):
    aliases = ref.build_aliases(data)
    owners = {a["food_code"] for a in aliases if a["normalized_alias"] == "roti" and a["is_preferred"]}
    assert owners == {"MAIN-19"}


def test_no_normalized_alias_is_preferred_twice(data):
    counts = Counter(a["normalized_alias"] for a in ref.build_aliases(data) if a["is_preferred"])
    assert [k for k, v in counts.items() if v > 1] == []


def test_validation_reports_every_problem_at_once(data):
    broken = ref.ReferenceData(
        foods=data.foods, food_nutrients=data.food_nutrients, groups=data.groups,
        curation={k: v for k, v in data.curation.items() if k != "MAIN-1"} | {"MAIN-999": data.curation["MAIN-2"]},
        manual_aliases=data.manual_aliases + [
            {"food_code": "NOPE-1", "alias": "x", "kind": "common", "is_preferred": "true"},
            {"food_code": "MAIN-18", "alias": "roti", "kind": "common", "is_preferred": "true"},
        ],
    )
    problems = "\n".join(ref.validate(broken))
    assert "MAIN-1 is missing from curation.csv" in problems
    assert "unknown food MAIN-999" in problems
    assert "unknown food NOPE-1" in problems
    assert "preferred for more than one food" in problems


def test_validation_rejects_negative_and_impossible_values(data):
    extra = [
        {"food_code": "MAIN-1", "nutrient_code": "protein_g", "amount_per_100g": "-1"},
    ]
    broken = ref.ReferenceData(data.foods, extra, data.groups, data.curation, data.manual_aliases)
    assert any("negative" in p for p in ref.validate(broken))
    heavy = [{"food_code": "MAIN-1", "nutrient_code": k, "amount_per_100g": "40"} for k in ("protein_g", "fat_g", "carbohydrate_g")]
    broken = ref.ReferenceData(data.foods, heavy, data.groups, data.curation, data.manual_aliases)
    assert any("over 105" in p for p in ref.validate(broken))


def test_energy_mismatch_flag():
    ok = {"energy_kcal": Decimal(400), "protein_g": Decimal(10), "fat_g": Decimal(10), "carbohydrate_g": Decimal(60)}
    assert ref.quality_flags(ok) == []  # 4*10 + 9*10 + 4*60 = 370, 7.5% off
    off = ok | {"energy_kcal": Decimal(200)}
    assert ref.quality_flags(off) == ["energy_mismatch"]
    assert ref.quality_flags({"energy_kcal": Decimal(200)}) == []  # missing macros: no flag

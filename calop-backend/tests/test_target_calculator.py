from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services import target_calculator as calc

TODAY = date(2026, 11, 8)


def run(sex="male", age=30, height=175, weight=85, activity="light", target=65, days=243):
    return calc.calculate_target(
        sex, age, Decimal(height), Decimal(weight), activity, Decimal(target), TODAY + timedelta(days=days), TODAY
    )


def test_bmr_and_maintenance_for_a_male():
    result = run(target=85, days=30)  # maintain
    # BMR = 10*85 + 6.25*175 - 5*30 + 5 = 1798.75; x 1.375
    assert result.goal_type == "maintain"
    assert result.maintenance_kcal == Decimal("2473.3")
    assert result.daily_adjustment_kcal == 0
    assert result.energy_kcal == result.maintenance_kcal


def test_female_bmr_uses_minus_161():
    male = run(sex="male", target=85, days=30)
    female = run(sex="female", target=85, days=30)
    assert abs((male.maintenance_kcal - female.maintenance_kcal) - Decimal("228.25")) <= Decimal("0.1")


def test_85_to_65_kg_in_8_months():
    result = run(target=65, days=243)  # about 8 months
    assert result.goal_type == "lose"
    assert result.warnings == []
    assert result.daily_adjustment_kcal == Decimal("-633.7")  # -20 * 7700 / 243
    assert abs(result.energy_kcal - (result.maintenance_kcal + result.daily_adjustment_kcal)) <= Decimal("0.1")
    assert not result.floor_applied
    # 30% protein, 30% fat, 40% carbs of energy
    assert abs(result.protein_g - result.energy_kcal * Decimal("0.30") / 4) <= Decimal("0.1")
    assert abs(result.fat_g - result.energy_kcal * Decimal("0.30") / 9) <= Decimal("0.1")
    assert abs(result.carbohydrate_g - result.energy_kcal * Decimal("0.40") / 4) <= Decimal("0.1")


def test_too_fast_goal_is_clamped_with_a_suggested_date():
    result = run(target=65, days=30)  # 20 kg in a month
    assert result.daily_adjustment_kcal == Decimal("-1100.0")
    warning = next(w for w in result.warnings if w.code == "goal_too_fast")
    assert warning.suggested_target_date == TODAY + timedelta(days=140)  # 20 kg at 1 kg per week


def test_calorie_floor_applies_and_suggests_a_date():
    result = run(sex="female", age=40, height=160, weight=60, activity="sedentary", target=50, days=60)
    assert result.floor_applied
    assert result.energy_kcal == Decimal("1200.0")
    warning = next(w for w in result.warnings if w.code == "calorie_floor")
    maintenance = result.maintenance_kcal
    assert maintenance > 1200
    expected_days = -(-(10 * 7700) // 1) / float(maintenance - 1200)
    assert warning.suggested_target_date is not None
    assert abs((warning.suggested_target_date - TODAY).days - expected_days) <= 1


def test_floor_without_a_date_when_maintenance_is_at_or_below_the_floor():
    result = run(sex="female", age=60, height=145, weight=40, activity="sedentary", target=35, days=30)
    assert result.floor_applied
    warning = next(w for w in result.warnings if w.code == "calorie_floor")
    assert warning.suggested_target_date is None


def test_maintain_within_half_a_kilo_ignores_the_date():
    result = run(target=Decimal("85.4"), days=0)
    assert result.goal_type == "maintain"
    assert abs(result.protein_g - result.energy_kcal * Decimal("0.20") / 4) <= Decimal("0.1")
    assert abs(result.carbohydrate_g - result.energy_kcal * Decimal("0.50") / 4) <= Decimal("0.1")


def test_gain_adds_calories_and_uses_the_gain_split():
    result = run(weight=60, target=66, days=120)
    assert result.goal_type == "gain"
    assert result.daily_adjustment_kcal == Decimal("385.0")  # 6 * 7700 / 120
    assert abs(result.fat_g - result.energy_kcal * Decimal("0.25") / 9) <= Decimal("0.1")


def test_a_past_target_date_is_rejected_for_a_real_goal():
    with pytest.raises(calc.InvalidTargetDate):
        run(target=65, days=0)


def test_age_in_years():
    assert calc.age_in_years(date(2000, 11, 9), date(2026, 11, 8)) == 25
    assert calc.age_in_years(date(2000, 11, 8), date(2026, 11, 8)) == 26


def test_inputs_record_every_value_used():
    inputs = run().inputs
    for key in ("sex", "age", "height_cm", "weight_kg", "activity_level", "activity_factor", "target_weight_kg",
                "target_date", "days", "bmr", "calorie_floor", "macro_split", "goal_type"):
        assert key in inputs

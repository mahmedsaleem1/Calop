"""The nutrient list of the Pakistan food composition table. Shared by the extraction script (header mapping),
the seed (the `nutrients` table) and `compute_nutrition` (which nutrients count as reported)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class NutrientDefinition:
    code: str
    name: str
    unit: str
    is_reported: bool
    headers: tuple[str, ...]


# Sort order is the order of this list.
NUTRIENTS: tuple[NutrientDefinition, ...] = (
    NutrientDefinition("energy_kcal", "Energy", "kcal", True, ("Food Energy (kcal)", "Energy (kcal)")),
    NutrientDefinition("protein_g", "Protein", "g", True, ("Protein (g)",)),
    NutrientDefinition("fat_g", "Fat", "g", True, ("Lipid / Fat (g)", "Fat (g)", "Fat / Oil (g)")),
    NutrientDefinition("carbohydrate_g", "Carbohydrate", "g", True, ("Carbohydrate (g)", "Carbohydrates (g)")),
    NutrientDefinition("fibre_g", "Fibre", "g", True, ("Fibre (g)",)),
    NutrientDefinition("calcium_mg", "Calcium", "mg", True, ("Calcium (mg)",)),
    NutrientDefinition("phosphorus_mg", "Phosphorus", "mg", True, ("Phosphorus (mg)",)),
    NutrientDefinition("iron_mg", "Iron", "mg", True, ("Iron (mg)",)),
    NutrientDefinition("zinc_mg", "Zinc", "mg", True, ("Zinc (mg)",)),
    NutrientDefinition("thiamin_mg", "Thiamin", "mg", True, ("Thiamin (mg)",)),
    NutrientDefinition("riboflavin_mg", "Riboflavin", "mg", True, ("Riboflavin (mg)",)),
    NutrientDefinition("niacin_mg", "Niacin", "mg", True, ("Niacin (mg)",)),
    NutrientDefinition("vitamin_c_mg", "Vitamin C", "mg", True, ("Vitamin C (mg)",)),
    NutrientDefinition("beta_carotene_ug", "β-Carotene", "µg", True, ("β-Carotene (mcg)",)),
    NutrientDefinition("vitamin_a_re", "Vitamin A", "RE", True, ("Vitamin A (RE)",)),
    NutrientDefinition("cholesterol_mg", "Cholesterol", "mg", True, ("Cholesterol (mg)",)),
    NutrientDefinition("moisture_g", "Moisture", "g", False, ("Moisture (g)",)),
    NutrientDefinition("ash_g", "Ash", "g", False, ("Ash (g)",)),
    # Units look wrong in the source, so it is stored but never reported.
    NutrientDefinition("iodine_ppm", "Iodine", "ppm", False, ("Iodine (ppm)",)),
)

HEADER_TO_NUTRIENT = {header: n.code for n in NUTRIENTS for header in n.headers}
REPORTED_CODES = frozenset(n.code for n in NUTRIENTS if n.is_reported)

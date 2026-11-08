from types import SimpleNamespace

from app.integrations.ai.food_recognizer import RecognizedCandidate
from app.services.recognition_service import decide

CATALOG = {
    "MAIN-19": SimpleNamespace(food_id=19),
    "MAIN-18": SimpleNamespace(food_id=18),
    "TRAD-13": SimpleNamespace(food_id=300),
}


def candidates(*pairs):
    return [RecognizedCandidate(code, confidence) for code, confidence in pairs]


def test_high_confidence_valid_code_is_logged_automatically():
    result = decide(candidates(("MAIN-19", 0.95), ("MAIN-18", 0.3)), CATALOG, 0.90)
    assert result.decision == "auto_logged"
    assert result.selected_food_id == 19
    assert result.top_confidence == 0.95
    assert [c[1:3] for c in result.candidates] == [("MAIN-19", 19), ("MAIN-18", 18)]


def test_exactly_the_threshold_counts():
    assert decide(candidates(("MAIN-19", 0.90)), CATALOG, 0.90).decision == "auto_logged"


def test_below_threshold_needs_review():
    result = decide(candidates(("MAIN-19", 0.71)), CATALOG, 0.90)
    assert result.decision == "needs_review"
    assert result.selected_food_id is None
    assert result.top_confidence == 0.71


def test_unknown_codes_are_kept_without_a_food_and_never_auto_logged():
    result = decide(candidates(("NOPE-1", 0.99)), CATALOG, 0.90)
    assert result.decision == "needs_review"
    assert result.candidates == [(1, "NOPE-1", None, 0.99)]
    assert result.top_confidence is None


def test_the_first_valid_candidate_decides_when_an_unknown_code_comes_first():
    result = decide(candidates(("NOPE-1", 0.99), ("TRAD-13", 0.92)), CATALOG, 0.90)
    assert result.decision == "auto_logged"
    assert result.selected_food_id == 300
    assert result.top_confidence == 0.92


def test_no_candidates_needs_review():
    result = decide([], CATALOG, 0.90)
    assert result.decision == "needs_review"
    assert result.candidates == []
    assert result.top_confidence is None

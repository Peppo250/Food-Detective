import pytest
from food_detective.modules.explainer import make_kid_explanation

def test_explainer_exact_match():
    # BHA explanation contains specific s1 + s2
    exp = make_kid_explanation("bha", "avoid", {})
    assert "preservative used to stop fats from going rotten" in exp

def test_explainer_phrase_boundary_match():
    # "bha preservative" should match BHA
    exp = make_kid_explanation("bha preservative", "avoid", {})
    assert "preservative used to stop fats from going rotten" in exp

def test_explainer_no_false_substring_match():
    # "canola oil" should NOT match "hydrogenated vegetable oil" or "palm oil"
    # It should fall back to the generic template
    exp = make_kid_explanation("canola oil", "safe", {})
    assert "Canola Oil is a type of fat or oil" in exp
    assert "trans fats" not in exp  # Should not match hydrogenated vegetable oil

    # "sodium" should NOT match "sodium benzoate"
    exp = make_kid_explanation("sodium", "safe", {})
    assert "Sodium is a type of salt" in exp
    assert "benzene" not in exp  # Should not match sodium benzoate

def test_explainer_toxic():
    exp = make_kid_explanation("bleach", "toxic", {})
    assert "cleaning chemical, NOT a food ingredient" in exp

def test_explainer_unknown():
    exp = make_kid_explanation("rare herb", "unknown", {})
    assert "couldn't find enough information" in exp

import pytest
from food_detective.modules.scorer import score_ingredient, overall_score

def test_score_toxic():
    assert score_ingredient({"name": "sodium hypochlorite"}) == "toxic"
    assert score_ingredient({"name": "bleach"}) == "toxic"

def test_score_avoid():
    # Avoid list colors
    assert score_ingredient({"name": "red 40"}) == "avoid"
    assert score_ingredient({"name": "tartrazine"}) == "avoid"
    
    # High adverse events
    assert score_ingredient({"name": "unknown chemical", "fda_adverse_events": 600}) == "avoid"

def test_score_caution():
    # Sugar, palm oil, salt, etc.
    assert score_ingredient({"name": "sugar"}) == "caution"
    assert score_ingredient({"name": "palm oil"}) == "caution"
    assert score_ingredient({"name": "maltodextrin"}) == "caution"

def test_score_safe():
    # Whole grains, water, vitamins
    assert score_ingredient({"name": "water"}) == "safe"
    assert score_ingredient({"name": "rolled oats"}) == "safe"
    assert score_ingredient({"name": "vitamin c"}) == "safe"

def test_score_unknown():
    assert score_ingredient({"name": "exotic plant extract"}) == "unknown"

def test_overall_score():
    # Great
    assert overall_score(["safe", "safe", "safe"]) == "great"
    assert overall_score(["safe", "safe", "safe", "caution"]) == "great"
    
    # Ok
    assert overall_score(["safe", "caution", "caution"]) == "ok"
    # 1 avoid out of 10 ingredients (10% ratio, not > 10%)
    assert overall_score(["safe"] * 9 + ["avoid"]) == "ok"
    
    # Bad
    assert overall_score(["safe", "avoid"]) == "bad"  # 1 avoid out of 2 ingredients (50% > 10%)
    assert overall_score(["safe", "avoid", "avoid"]) == "bad"  # 2 avoids
    
    # Not food
    assert overall_score(["safe", "toxic"]) == "not_food"

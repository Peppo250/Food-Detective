"""
modules/daily_limits.py — Daily intake limits and serving-based safety scoring.

Data sources:
  - WHO guidelines for children (4-8 years)
  - American Heart Association (AHA) children's sugar/sodium limits
  - EFSA acceptable daily intakes (ADIs) for food additives
  - FDA reference daily intakes (RDIs)

Reference child: 20 kg (typical 4-8 year old). Parents of older children
can interpret numbers loosely — the limits are always conservative.
"""

import re
from dataclasses import dataclass
from typing import Optional
import os

DEFAULT_CHILD_WEIGHT = float(os.getenv("FOOD_DETECTIVE_CHILD_WEIGHT", "20.0"))

# ---------------------------------------------------------------------------
# Daily limit database
# ---------------------------------------------------------------------------

@dataclass
class DailyLimit:
    name: str
    limit_g: float          # flat daily limit in grams (0 = use ADI calc)
    unit: str = "g"
    adi_per_kg: float = 0.0 # EFSA/WHO ADI in mg per kg bodyweight (0 = not set)
    child_kg: float = DEFAULT_CHILD_WEIGHT  # reference child weight
    source: str = ""
    notes: str = ""

    @property
    def effective_limit_g(self) -> float:
        if self.adi_per_kg > 0:
            return (self.adi_per_kg * self.child_kg) / 1000.0  # mg -> g
        return self.limit_g

    @property
    def effective_limit_display(self) -> str:
        lim = self.effective_limit_g
        if self.unit == "mg":
            return f"{lim*1000:.0f} mg"
        return f"{lim:.1f} g"


LIMITS: dict[str, DailyLimit] = {
    # ── Macronutrients ────────────────────────────────────────────────────

    "sugar": DailyLimit(
        "Added Sugar", 25.0, "g",
        source="AHA 2016 — max 25 g/day for children",
        notes="About 6 teaspoons. Natural fruit sugars don't count."),
    "glucose":        DailyLimit("Glucose",       25.0, "g", source="AHA"),
    "fructose":       DailyLimit("Fructose",       25.0, "g", source="AHA"),
    "dextrose":       DailyLimit("Dextrose",       25.0, "g", source="AHA"),
    "sucrose":        DailyLimit("Sucrose",        25.0, "g", source="AHA"),
    "liquid glucose": DailyLimit("Liquid Glucose", 25.0, "g", source="AHA"),
    "corn syrup":     DailyLimit("Corn Syrup",     20.0, "g", source="AHA"),
    "high fructose corn syrup": DailyLimit("HFCS", 15.0, "g", source="AHA — stricter"),
    "honey":          DailyLimit("Honey",          25.0, "g", source="AHA — counts as added sugar"),
    "maltose":        DailyLimit("Maltose",        25.0, "g", source="AHA"),

    "salt": DailyLimit(
        "Salt", 2.0, "g",
        source="WHO 2012 — children 4-8: < 2 g salt/day (800 mg sodium)",
        notes="2 g salt = 800 mg sodium. Most children already exceed this daily."),
    "sodium":        DailyLimit("Sodium",      0.8,  "g", source="WHO — 800 mg/day"),
    "iodized salt":  DailyLimit("Salt",        2.0,  "g", source="WHO"),
    "iodised salt":  DailyLimit("Salt",        2.0,  "g", source="WHO"),
    "lodized salt":  DailyLimit("Salt",        2.0,  "g", source="WHO"),
    "lodised salt":  DailyLimit("Salt",        2.0,  "g", source="WHO"),
    "sea salt":      DailyLimit("Salt",        2.0,  "g", source="WHO"),

    "saturated fat": DailyLimit("Saturated Fat", 16.0, "g", source="DRI — < 10% of 1400 kcal"),
    "total fat":     DailyLimit("Total Fat",     49.0, "g", source="DRI — 35% of 1400 kcal"),
    "palm oil":      DailyLimit("Palm Oil",       8.0, "g", source="EFSA — high saturated fat"),

    # ── Artificial colours ────────────────────────────────────────────────

    "red 40": DailyLimit(
        "Red 40 (Allura Red)", 0.0, "mg", adi_per_kg=7.0,
        source="EFSA 2015",
        notes="EU warning label required. Best avoided entirely by children."),
    "allura red":    DailyLimit("Red 40",  0.0, "mg", adi_per_kg=7.0,  source="EFSA"),
    "yellow 5":      DailyLimit("Yellow 5 (Tartrazine)", 0.0, "mg", adi_per_kg=7.5,
        source="EFSA 2009", notes="EU warning label required. Linked to hyperactivity."),
    "tartrazine":    DailyLimit("Yellow 5", 0.0, "mg", adi_per_kg=7.5, source="EFSA"),
    "yellow 6":      DailyLimit("Yellow 6 (Sunset Yellow)", 0.0, "mg", adi_per_kg=7.5, source="EFSA"),
    "sunset yellow": DailyLimit("Yellow 6", 0.0, "mg", adi_per_kg=7.5, source="EFSA"),
    "blue 1":        DailyLimit("Blue 1 (Brilliant Blue)", 0.0, "mg", adi_per_kg=12.5, source="EFSA"),
    "blue 2":        DailyLimit("Blue 2", 0.0, "mg", adi_per_kg=5.0,  source="EFSA"),
    "red 3":         DailyLimit("Red 3",  0.0, "mg", adi_per_kg=0.1,  source="FDA — banned in cosmetics"),
    "green 3":       DailyLimit("Green 3", 0.0, "mg", adi_per_kg=25.0, source="FDA"),
    "artificial color":  DailyLimit("Artificial Color",  0.0, "mg", adi_per_kg=7.0, source="EFSA — conservative"),
    "artificial colour": DailyLimit("Artificial Colour", 0.0, "mg", adi_per_kg=7.0, source="EFSA"),
    "caramel color iv":  DailyLimit("Caramel Color IV", 0.0, "mg", adi_per_kg=0.0,
        source="IARC 2B possible carcinogen (4-MEI)",
        notes="No safe daily limit established. California Prop 65 listed."),
    "caramel colour iv": DailyLimit("Caramel Colour IV", 0.0, "mg", adi_per_kg=0.0, source="IARC"),

    # ── Preservatives ─────────────────────────────────────────────────────

    "sodium benzoate": DailyLimit(
        "Sodium Benzoate", 0.0, "mg", adi_per_kg=5.0,
        source="EFSA/WHO",
        notes="Forms benzene when combined with Vitamin C. Best avoided."),
    "potassium benzoate": DailyLimit("Potassium Benzoate", 0.0, "mg", adi_per_kg=5.0, source="EFSA"),
    "bha": DailyLimit(
        "BHA", 0.0, "mg", adi_per_kg=0.5,
        source="EFSA 2012",
        notes="Possible carcinogen. ADI is only 0.5 mg/kg — very small amount."),
    "bht":  DailyLimit("BHT",  0.0, "mg", adi_per_kg=0.25, source="EFSA"),
    "tbhq": DailyLimit("TBHQ", 0.0, "mg", adi_per_kg=0.7,  source="EFSA"),
    "sodium nitrate":  DailyLimit("Sodium Nitrate",  0.0, "mg", adi_per_kg=3.7, source="WHO"),
    "sodium nitrite":  DailyLimit("Sodium Nitrite",  0.0, "mg", adi_per_kg=0.07,
        source="EFSA — extremely low ADI",
        notes="ADI is only 0.07 mg/kg. Even tiny amounts in processed meat are concerning."),
    "potassium sorbate":  DailyLimit("Potassium Sorbate",  0.0, "mg", adi_per_kg=25.0, source="EFSA"),
    "sulfur dioxide":     DailyLimit("Sulphur Dioxide",    0.0, "mg", adi_per_kg=0.7,  source="EFSA"),
    "sodium metabisulfite": DailyLimit("Sodium Metabisulfite", 0.0, "mg", adi_per_kg=0.7, source="EFSA"),

    # ── Artificial sweeteners ─────────────────────────────────────────────

    "aspartame": DailyLimit(
        "Aspartame", 0.0, "mg", adi_per_kg=40.0,
        source="EFSA 2013 / FDA",
        notes="IARC classified as possibly carcinogenic (Group 2B) in 2023."),
    "saccharin":         DailyLimit("Saccharin",         0.0, "mg", adi_per_kg=5.0,  source="EFSA"),
    "acesulfame potassium": DailyLimit("Acesulfame-K",   0.0, "mg", adi_per_kg=9.0,  source="EFSA"),
    "acesulfame-k":      DailyLimit("Acesulfame-K",      0.0, "mg", adi_per_kg=9.0,  source="EFSA"),
    "sucralose":         DailyLimit("Sucralose",          0.0, "mg", adi_per_kg=15.0, source="EFSA"),
    "cyclamate":         DailyLimit("Cyclamate",          0.0, "mg", adi_per_kg=7.0,  source="EFSA"),

    # ── Flavour enhancers ─────────────────────────────────────────────────

    "monosodium glutamate": DailyLimit(
        "MSG", 0.0, "mg", adi_per_kg=30.0,
        source="EFSA 2017",
        notes="Headaches reported above 3 g in sensitive adults."),
    "msg": DailyLimit("MSG", 0.0, "mg", adi_per_kg=30.0, source="EFSA"),
    "disodium guanylate": DailyLimit(
        "Disodium Guanylate", 0.0, "mg", adi_per_kg=0.0,
        source="No ADI established", notes="Use sparingly."),
    "disodium inosinate": DailyLimit(
        "Disodium Inosinate", 0.0, "mg", adi_per_kg=0.0,
        source="No ADI established", notes="Use sparingly."),

    # ── Other additives ───────────────────────────────────────────────────

    "carrageenan": DailyLimit(
        "Carrageenan", 0.0, "mg", adi_per_kg=75.0,
        source="EFSA 2018",
        notes="No longer approved for infant formula in the EU. Gut inflammation concern."),
    "maltodextrin": DailyLimit("Maltodextrin", 10.0, "g", source="General guidance — high GI"),
    "xanthan gum":  DailyLimit("Xanthan Gum",  0.0, "mg", adi_per_kg=10.0, source="EFSA"),
    "acetylated distarch adipate": DailyLimit(
        "Modified Starch (E1422)", 0.0, "mg", adi_per_kg=0.0,
        source="No ADI established"),
    "caramel color i":   DailyLimit("Caramel Color I",   0.0, "mg", adi_per_kg=0.0, source="No ADI"),
    "caramel colour i":  DailyLimit("Caramel Colour I",  0.0, "mg", adi_per_kg=0.0, source="No ADI"),
}


# ---------------------------------------------------------------------------
# Serving size parser — extracts from OCR text
# ---------------------------------------------------------------------------

_SERVING_RE = [
    re.compile(r"serving\s+size\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(g|ml|oz|pieces?|biscuits?|cookies?|chips?|crackers?)", re.I),
    re.compile(r"per\s+serving\s*\(?(\d+(?:\.\d+)?)\s*(g|ml|oz)\)?", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*(g|ml|oz)\s+per\s+serving", re.I),
    re.compile(r"per\s+(\d+(?:\.\d+)?)\s*(g|ml)", re.I),
]
_UNIT_G = {"g":1.0,"ml":1.0,"oz":28.35,"piece":10.0,"biscuit":10.0,"cookie":15.0,"chip":2.0,"cracker":5.0}


def parse_serving_size(text: str) -> Optional[float]:
    """Extract serving size in grams from label text. Returns None if not found."""
    for pat in _SERVING_RE:
        m = pat.search(text[:600])
        if m:
            amount = float(m.group(1))
            unit = m.group(2).lower().rstrip("s")
            g = amount * _UNIT_G.get(unit, 1.0)
            if 3 <= g <= 1000:
                return g
    return None


# ---------------------------------------------------------------------------
# Nutriment parser — extracts per-serving amounts from OCR text
# ---------------------------------------------------------------------------

_NUTRIMENT_RE = {
    "sugar":         re.compile(r"sugars?\s+(\d+(?:\.\d+)?)\s*(g|mg)", re.I),
    "sodium":        re.compile(r"sodium\s+(\d+(?:\.\d+)?)\s*(g|mg)", re.I),
    "salt":          re.compile(r"\bsalt\b\s+(\d+(?:\.\d+)?)\s*(g|mg)", re.I),
    "total fat":     re.compile(r"total\s+fat\s+(\d+(?:\.\d+)?)\s*(g|mg)", re.I),
    "saturated fat": re.compile(r"sat(?:urated)?\s+fat\s+(\d+(?:\.\d+)?)\s*(g|mg)", re.I),
    "calories":      re.compile(r"(?:calories?|energy)\s+(\d+(?:\.\d+)?)", re.I),
}


def parse_nutriments(text: str) -> dict[str, float]:
    """Extract per-serving nutrient amounts (in grams) from label text."""
    result = {}
    for name, pat in _NUTRIMENT_RE.items():
        m = pat.search(text)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower() if m.lastindex >= 2 else "g"
            result[name] = val / 1000.0 if unit == "mg" else val
    # Derive salt from sodium if not found
    if "salt" not in result and "sodium" in result:
        result["salt"] = result["sodium"] * 2.5
    return result


# ---------------------------------------------------------------------------
# Advice computation
# ---------------------------------------------------------------------------

# Typical per-serving amounts (mg) for additives that don't appear in
# nutrition panels — based on regulatory survey data
_ADDITIVE_TYPICAL_MG = {
    "red 40": 15.0,      "allura red": 15.0,
    "yellow 5": 10.0,    "tartrazine": 10.0,
    "yellow 6": 10.0,    "sunset yellow": 10.0,
    "blue 1": 5.0,       "blue 2": 5.0,
    "sodium benzoate": 50.0, "potassium benzoate": 50.0,
    "bha": 0.5,          "bht": 0.5,       "tbhq": 1.0,
    "aspartame": 50.0,   "saccharin": 20.0,
    "acesulfame potassium": 20.0, "acesulfame-k": 20.0,
    "sucralose": 10.0,
    "monosodium glutamate": 300.0, "msg": 300.0,
    "sodium nitrate": 15.0, "sodium nitrite": 3.0,
    "carrageenan": 150.0,
    "artificial color": 10.0, "artificial colour": 10.0,
    "caramel color iv": 80.0, "caramel colour iv": 80.0,
}


@dataclass
class IngredientAdvice:
    ingredient: str
    display_name: str
    limit_display: str          # "25 g/day", "140 mg/day"
    per_serving_display: str    # "12 g per serving", "15 mg per serving"
    max_servings: float
    max_servings_display: str   # "2", "1", "about 3", "less than 1"
    source: str
    notes: str
    is_concern: bool            # True if max_servings <= 1


@dataclass
class ProductAdvice:
    serving_size_g: Optional[float]
    nutriments: dict
    limiting_ingredient: str
    max_servings: float
    max_servings_display: str
    summary: str                # one-sentence kid-friendly verdict
    detail_lines: list[str]     # per-ingredient breakdown
    all_advice: list            # list of IngredientAdvice


def compute_product_advice(
    ingredients: list[str],
    ocr_text: str,
    product_name: str = "this product",
) -> ProductAdvice:
    """
    Given parsed ingredients and raw OCR text, compute how many servings
    of this product a child can safely have per day.
    """
    serving_size_g = parse_serving_size(ocr_text)
    nutriments = parse_nutriments(ocr_text)
    advice_list: list[IngredientAdvice] = []

    # 1. Check nutrition panel data (most accurate)
    nutriment_map = {
        "sugar": "sugar", "sodium": "sodium", "salt": "salt",
        "total fat": "total fat", "saturated fat": "saturated fat",
    }
    for nutr_key, ing_key in nutriment_map.items():
        if nutr_key not in nutriments:
            continue
        per_g = nutriments[nutr_key]
        adv = _make_advice(ing_key, per_g, product_name, is_mg=False)
        if adv:
            advice_list.append(adv)

    # 2. Check ingredients against additive typical amounts
    seen_ingredients = set()
    for ing in ingredients:
        key = ing.lower().strip()
        if key in seen_ingredients:
            continue
        if key in _ADDITIVE_TYPICAL_MG:
            seen_ingredients.add(key)
            per_mg = _ADDITIVE_TYPICAL_MG[key]
            adv = _make_advice(key, per_mg / 1000.0, product_name, is_mg=True)
            if adv:
                advice_list.append(adv)

    # 3. Flag ALL AVOID-list ingredients for the warning section
    from food_detective.modules.scorer import AVOID as AVOID_SET
    avoid_found = [
        ing for ing in ingredients
        if ing.lower().strip() in AVOID_SET
    ]

    if not advice_list and not avoid_found:
        return ProductAdvice(
            serving_size_g=serving_size_g,
            nutriments=nutriments,
            limiting_ingredient="",
            max_servings=999,
            max_servings_display="no limit found",
            summary=(
                "We couldn't find serving size or nutrition info on this label. "
                "Check the nutrition panel on the packaging for daily intake guidance."
            ),
            detail_lines=[],
            all_advice=[],
        )

    # Sort: most restrictive (lowest max_servings) first
    advice_list.sort(key=lambda a: a.max_servings)

    # Separate "no safe limit" from limited ones
    no_limit = [a for a in advice_list if a.max_servings == 0]
    limited  = [a for a in advice_list if a.max_servings > 0]
    most_restrictive = limited[0] if limited else (advice_list[0] if advice_list else None)

    # Build summary
    if avoid_found and not advice_list:
        names = ", ".join(a.title() for a in avoid_found[:3])
        summary = (
            f"⚠️ This product contains {names} — ingredient(s) that are best "
            f"avoided by children regardless of quantity. Limit to as few servings "
            f"as possible, ideally none."
        )
        max_display = "as few as possible"
        limiting = avoid_found[0]
    elif avoid_found:
        names = ", ".join(a.title() for a in avoid_found[:2])
        n = most_restrictive.max_servings_display
        summary = (
            f"⚠️ This product contains {names} which children should avoid. "
            f"Based on nutrition data, limit to {n} serving(s) per day max."
        )
        max_display = most_restrictive.max_servings_display
        limiting = most_restrictive.ingredient
    elif no_limit:
        names = " and ".join(a.display_name for a in no_limit[:2])
        summary = (
            f"🚫 This product contains {names}, which has no established safe daily "
            f"limit for children. It's best to avoid it."
        )
        max_display = "none"
        limiting = no_limit[0].ingredient
    elif most_restrictive.max_servings < 0.5:
        summary = (
            f"⚠️ Even one serving has too much {most_restrictive.display_name} "
            f"for a child! The daily limit is {most_restrictive.limit_display}."
        )
        max_display = most_restrictive.max_servings_display
        limiting = most_restrictive.ingredient
    elif most_restrictive.max_servings < 1.5:
        summary = (
            f"🍫 A child can have at most 1 serving of {product_name} per day — "
            f"limited by {most_restrictive.display_name} "
            f"({most_restrictive.per_serving_display} per serving, "
            f"daily limit: {most_restrictive.limit_display})."
        )
        max_display = "1"
        limiting = most_restrictive.ingredient
    else:
        n = most_restrictive.max_servings_display
        summary = (
            f"✅ A child can safely have up to {n} serving(s) of {product_name} "
            f"per day — limited by {most_restrictive.display_name} "
            f"({most_restrictive.limit_display} daily limit)."
        )
        max_display = n
        limiting = most_restrictive.ingredient

    # Build detail lines — only show ingredients that actually limit consumption
    detail_lines = []
    shown = set()

    # First: AVOID-list ingredients get a special warning line
    for ing in avoid_found:
        detail_lines.append(f"🚫 {ing.title()}: best avoided entirely by children")

    avoid_found_keys = {a.lower() for a in avoid_found}
    for adv in advice_list:
        key = adv.ingredient
        if key in shown or key in avoid_found_keys:
            continue
        shown.add(key)
        if adv.max_servings > 5 and not adv.is_concern:
            continue
        if adv.max_servings == 0:
            detail_lines.append(f"☠️ {adv.display_name}: no established safe daily limit")
        elif adv.max_servings < 0.5:
            detail_lines.append(
                f"🚫 {adv.display_name}: max < ½ serving/day  "
                f"[{adv.per_serving_display} · limit {adv.limit_display}]"
            )
        elif adv.max_servings < 1.5:
            detail_lines.append(
                f"⚠️ {adv.display_name}: max 1 serving/day  "
                f"[{adv.per_serving_display} · limit {adv.limit_display}]"
            )
        else:
            detail_lines.append(
                f"✅ {adv.display_name}: up to {adv.max_servings_display} servings/day  "
                f"[limit {adv.limit_display}]"
            )

    return ProductAdvice(
        serving_size_g=serving_size_g,
        nutriments=nutriments,
        limiting_ingredient=limiting,
        max_servings=most_restrictive.max_servings if most_restrictive else 999,
        max_servings_display=max_display,
        summary=summary,
        detail_lines=detail_lines,
        all_advice=advice_list,
    )


def _make_advice(
    key: str,
    per_serving_g: float,
    product_name: str,
    is_mg: bool,
) -> Optional[IngredientAdvice]:
    """Build an IngredientAdvice for one ingredient."""
    dl = LIMITS.get(key)
    if not dl or per_serving_g <= 0:
        return None

    limit_g = dl.effective_limit_g

    # No ADI established — flag as no safe limit
    if limit_g == 0 and dl.adi_per_kg == 0:
        return IngredientAdvice(
            ingredient=key,
            display_name=dl.name,
            limit_display="no safe limit",
            per_serving_display=_fmt_amount(per_serving_g, dl.unit),
            max_servings=0,
            max_servings_display="none",
            source=dl.source,
            notes=dl.notes,
            is_concern=True,
        )

    max_servings = limit_g / per_serving_g
    display = _fmt_servings(max_servings)
    is_concern = max_servings <= 1.0

    return IngredientAdvice(
        ingredient=key,
        display_name=dl.name,
        limit_display=dl.effective_limit_display,
        per_serving_display=_fmt_amount(per_serving_g, dl.unit),
        max_servings=max_servings,
        max_servings_display=display,
        source=dl.source,
        notes=dl.notes,
        is_concern=is_concern,
    )


def _fmt_servings(n: float) -> str:
    if n < 0.5:   return "less than ½"
    if n < 0.75:  return "½"
    if n < 1.25:  return "1"
    if n < 1.75:  return "1½"
    if n < 2.5:   return "2"
    if n < 10:    return str(int(round(n)))
    return f"about {int(n)}"


def _fmt_amount(g: float, unit: str) -> str:
    if unit == "mg":
        mg = g * 1000
        return f"{mg:.1f} mg"
    return f"{g:.1f} g"

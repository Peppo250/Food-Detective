"""
modules/explainer.py — Generate child-friendly explanations for ingredients.

Uses a combination of:
  1. Hardcoded explanations for the most common harmful additives
     (these are the best quality — hand-crafted for 6–12 year olds)
  2. Template-based generation from API data for everything else

Target reading level: Grade 3–5 (ages 8–11)
Rules:
  - Short sentences. Max 15 words per sentence.
  - No scientific jargon without immediate plain-English follow-up.
  - Avoid scary language for "caution" items — just factual.
  - Use analogies kids understand (colours, sugar, sweets).
"""

# ---------------------------------------------------------------------------
# Hardcoded explanations for top harmful additives
# ---------------------------------------------------------------------------

_KNOWN = {
    # Colours
    "red 40": (
        "Red 40 is a fake red colour made in a lab from oil.",
        "Some kids feel more hyper or restless after eating it.",
    ),
    "allura red": (
        "Allura Red (also called Red 40) is an artificial food dye.",
        "Studies show it can make some children harder to sit still.",
    ),
    "yellow 5": (
        "Yellow 5 is a bright yellow dye made from chemicals.",
        "It can cause allergic reactions and make some kids more hyper.",
    ),
    "tartrazine": (
        "Tartrazine is another name for Yellow 5, an artificial dye.",
        "In Europe, foods with it must have a warning label for children!",
    ),
    "yellow 6": (
        "Yellow 6 is an orange-yellow artificial colour.",
        "It can trigger allergies and may affect how some kids behave.",
    ),
    "blue 1": (
        "Blue 1 is a bright blue dye made from coal tar or oil.",
        "It can cause allergic reactions in some people.",
    ),
    "green 3": (
        "Green 3 is a synthetic green food colour.",
        "Scientists are still studying whether it's safe in large amounts.",
    ),
    "red 3": (
        "Red 3 is a cherry-red artificial dye.",
        "The USA banned it in cosmetics but it's still allowed in some foods.",
    ),

    # Preservatives
    "sodium benzoate": (
        "Sodium benzoate is a preservative that stops food going bad.",
        "When mixed with Vitamin C in drinks, it can turn into a harmful chemical called benzene.",
    ),
    "bha": (
        "BHA is a preservative used to stop fats from going rotten.",
        "It is listed as a possible cancer-causing chemical by some health organisations.",
    ),
    "butylated hydroxyanisole": (
        "This long word is just another name for BHA — a chemical preservative.",
        "Some scientists worry it might cause cancer if eaten a lot over time.",
    ),
    "bht": (
        "BHT is similar to BHA — it's added to keep fats from going bad.",
        "Some studies in animals have found it can cause health problems.",
    ),
    "tbhq": (
        "TBHQ is a preservative found in many snack foods and fast food.",
        "Eating too much of it has been linked to health problems in animal studies.",
    ),
    "sodium nitrate": (
        "Sodium nitrate is added to meat like hot dogs and bacon to keep its pink colour.",
        "Inside our body it can turn into chemicals called nitrosamines, which aren't healthy.",
    ),
    "sodium nitrite": (
        "Sodium nitrite preserves meat and gives it a pink look.",
        "It's the same story as sodium nitrate — can form unhealthy chemicals in your body.",
    ),

    # Sweeteners
    "aspartame": (
        "Aspartame is an artificial sweetener used instead of sugar.",
        "It's very controversial — many scientists disagree about whether it's safe.",
    ),
    "saccharin": (
        "Saccharin was one of the first artificial sweeteners ever made.",
        "It used to have a cancer warning label — it was removed but many still avoid it.",
    ),
    "acesulfame potassium": (
        "Acesulfame-K is a zero-calorie artificial sweetener.",
        "We don't have many studies on how it affects children specifically.",
    ),
    "acesulfame-k": (
        "Acesulfame-K is a zero-calorie artificial sweetener.",
        "We don't have many studies on how it affects children specifically.",
    ),

    # MSG
    "monosodium glutamate": (
        "MSG is a flavour booster added to make salty snacks taste stronger.",
        "Some people get headaches, flushing or feel sick after eating a lot of it.",
    ),
    "msg": (
        "MSG makes food taste more savoury — like the flavour is turned up.",
        "Some kids get headaches or upset stomachs from eating too much of it.",
    ),

    # Sugars
    "high fructose corn syrup": (
        "High fructose corn syrup is a very sweet liquid made from corn.",
        "It's in many soft drinks and snacks and is linked to weight gain and tooth decay.",
    ),
    "hfcs": (
        "HFCS is short for high fructose corn syrup — a very sweet liquid from corn.",
        "Eating too much is linked to obesity, diabetes and tooth decay.",
    ),

    # Oils
    "partially hydrogenated": (
        "This means the fat has been chemically changed to last longer.",
        "These 'trans fats' are very bad for your heart and most countries have banned them!",
    ),
    "hydrogenated vegetable oil": (
        "Hydrogenated oil is vegetable oil that has been processed to become solid.",
        "It creates trans fats, which are really bad for your heart.",
    ),

    # Carrageenan
    "carrageenan": (
        "Carrageenan is extracted from red seaweed and used to thicken foods.",
        "Some scientists think it can irritate our gut and cause inflammation.",
    ),
}

# ---------------------------------------------------------------------------
# Templates for status-based generation
# ---------------------------------------------------------------------------

_AVOID_TEMPLATE = (
    "{name} is added to food to {purpose}. "
    "It's best for kids to avoid it because {concern}."
)

_CAUTION_TEMPLATE = (
    "{name} is {what}. "
    "It's okay in small amounts, but too much {concern}."
)

_SAFE_TEMPLATE = (
    "{name} is {what}. "
    "This is a natural ingredient that gives your body {benefit}!"
)

_UNKNOWN_TEMPLATE = (
    "We found {name} in this product. "
    "We couldn't find enough information about it right now."
)

# Purposes map (for avoid items not in _KNOWN)
_PURPOSES = {
    "e": "preserve colour or taste",
    "colour": "add colour",
    "color": "add colour",
    "preserve": "make it last longer on the shelf",
    "sweet": "make it taste sweeter",
    "flavor": "boost the flavour",
    "flavour": "boost the flavour",
}

# Generic concerns
_CONCERN_AVOID = "it can affect behaviour, cause allergies, or has been linked to health problems in studies"
_CONCERN_CAUTION = "can add up to more sugar, salt, or processed fat than is good for you"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def make_kid_explanation(name: str, status: str, data: dict) -> str:
    """
    Build a child-friendly 1–2 sentence explanation.
    Returns a plain string ready to display.
    """
    # Toxic / non-food chemicals — strong clear warning
    if status == "toxic":
        return (
            f"{name.title()} is a cleaning chemical, NOT a food ingredient. "
            "This product is NOT safe to eat — it looks like a cleaning product or disinfectant!"
        )
    key = name.lower().strip()

    # 1. Try hardcoded best-quality explanations first
    for known_key, (sent1, sent2) in _KNOWN.items():
        if known_key in key or key in known_key:
            return sent1 + " " + sent2

    # 2. Use Wikipedia summary if we have it and it's short enough
    wiki_summary = data.get("summary", "")
    if wiki_summary and len(wiki_summary) < 300:
        simplified = _simplify(wiki_summary)
        if simplified:
            if status == "avoid":
                return simplified + " It's best for children to avoid this ingredient."
            elif status == "caution":
                return simplified + " It's okay in small amounts, but watch out for too much."
            elif status == "safe":
                return simplified + " This is generally a good, natural ingredient!"

    # 3. Template fallback
    if status == "avoid":
        purpose = _guess_purpose(name)
        return _AVOID_TEMPLATE.format(
            name=name.title(), purpose=purpose, concern=_CONCERN_AVOID
        )
    elif status == "caution":
        what = _guess_what(name, data)
        return _CAUTION_TEMPLATE.format(
            name=name.title(), what=what, concern=_CONCERN_CAUTION
        )
    elif status == "safe":
        what = _guess_what(name, data)
        benefit = _guess_benefit(name)
        return _SAFE_TEMPLATE.format(name=name.title(), what=what, benefit=benefit)
    else:
        return _UNKNOWN_TEMPLATE.format(name=name.title())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simplify(text: str) -> str:
    """Keep first sentence only; replace jargon with simpler words."""
    import re
    # First sentence only
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    result = sentences[0] if sentences else text

    # Replace common jargon
    replacements = [
        (r"\bsynthetic\b", "man-made"),
        (r"\bsynthesized\b", "made in a lab"),
        (r"\bsynthesised\b", "made in a lab"),
        (r"\bcompound\b", "chemical"),
        (r"\bsubstance\b", "ingredient"),
        (r"\bconsumed\b", "eaten"),
        (r"\bingested\b", "swallowed"),
        (r"\badminister\b", "give"),
        (r"\bderived from\b", "made from"),
        (r"\butilised\b", "used"),
        (r"\butilized\b", "used"),
        (r"\bcommonly known as\b", "also called"),
    ]
    import re
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # Truncate if still long
    if len(result) > 200:
        result = result[:197] + "..."

    return result.strip()


def _guess_purpose(name: str) -> str:
    name_lower = name.lower()
    for keyword, purpose in _PURPOSES.items():
        if keyword in name_lower:
            return purpose
    return "improve taste or appearance"


def _guess_what(name: str, data: dict) -> str:
    name_lower = name.lower()
    if any(w in name_lower for w in ["sugar", "syrup", "glucose", "fructose", "dextrose"]):
        return "a type of sugar"
    if any(w in name_lower for w in ["oil", "fat"]):
        return "a type of fat or oil"
    if any(w in name_lower for w in ["salt", "sodium"]):
        return "a type of salt"
    if any(w in name_lower for w in ["starch", "flour"]):
        return "a starchy ingredient"
    if any(w in name_lower for w in ["colour", "color", "dye"]):
        return "an artificial colour"
    if data.get("e_number"):
        return f"a food additive ({data['e_number']})"
    return "an ingredient"


def _guess_benefit(name: str) -> str:
    name_lower = name.lower()
    if any(w in name_lower for w in ["vitamin", "mineral", "calcium", "iron", "zinc"]):
        return "important vitamins and minerals"
    if any(w in name_lower for w in ["protein", "egg", "milk", "whey"]):
        return "protein to help you grow strong"
    if any(w in name_lower for w in ["fibre", "fiber", "grain", "oat"]):
        return "fibre to keep your tummy happy"
    if any(w in name_lower for w in ["fruit", "vegetable", "berry", "apple", "carrot"]):
        return "natural vitamins from plants"
    return "good nutrition"

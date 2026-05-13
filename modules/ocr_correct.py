"""
modules/ocr_correct.py — Fuzzy OCR error correction for ingredient names.

EasyOCR commonly misreads:
  b <-> h  (barlev -> barley, honev -> honey)
  y <-> v  (sovbean -> soybean)
  l <-> 1  (whey 1 protein -> whey protein)
  gh added (pyrophosghate -> pyrophosphate)
  { } from bracket confusion

Strategy:
  1. Regex-based exact typo fixes for highest-frequency OCR errors
  2. Fuzzy match each token against a known ingredient dictionary
     using rapidfuzz (token_sort_ratio >= 88%)
  3. Remove non-ingredient descriptor phrases
  4. Merge split oil tokens (canola -> canola oil)
"""

import re

# ---------------------------------------------------------------------------
# 1. Regex typo fixes applied to the whole OCR text before parsing
# ---------------------------------------------------------------------------

_TYPO_FIXES = [
    (re.compile(r'\barlev\b',          re.I), 'arley'),
    (re.compile(r'\bhonev\b',          re.I), 'honey'),
    (re.compile(r'\bsovbean\b',        re.I), 'soybean'),
    (re.compile(r'\bsoyabean\b',       re.I), 'soybean'),
    (re.compile(r'\bpyrophosghate\b',  re.I), 'pyrophosphate'),
    (re.compile(r'\bwhev\b',           re.I), 'whey'),
    (re.compile(r'\bniacm\b',          re.I), 'niacin'),
    (re.compile(r'\briboflav[il]n\b',  re.I), 'riboflavin'),
    (re.compile(r'\bthiamm\b',         re.I), 'thiamin'),
    (re.compile(r'\bascorb[il]c\b',    re.I), 'ascorbic'),
    (re.compile(r'\bglucouse\b',       re.I), 'glucose'),
    (re.compile(r'\bcornmea[il]\b',    re.I), 'cornmeal'),
    (re.compile(r'\bfloiir\b',         re.I), 'flour'),
    (re.compile(r'\blod[il]z[eo]d\b',  re.I), 'iodized'),
    (re.compile(r'\blod[il]s[eo]d\b',  re.I), 'iodised'),
    (re.compile(r'\bcalc[il]um\b',     re.I), 'calcium'),
    (re.compile(r'\bsod[il]um\b',      re.I), 'sodium'),
    (re.compile(r'\bpotass[il]um\b',   re.I), 'potassium'),
    (re.compile(r'\bmono[s5]od[il]um\b', re.I), 'monosodium'),
    (re.compile(r'\bpalmole[il]n\b',   re.I), 'palmolein'),
    (re.compile(r'\bwh[e3]y\b',        re.I), 'whey'),
    (re.compile(r'(\bwhey)\s+[1l]\s+(protein\b)', re.I), r'\1 \2'),
    (re.compile(r'\b0il\b'),                    'oil'),
    (re.compile(r'\boi[il]\b',         re.I),   'oil'),
    (re.compile(r'\bascorbic\s+acid\s+dough\s+conditioner\b', re.I), 'ascorbic acid'),
    (re.compile(r'[\{\}\[\]\\|]'),              ' '),
    (re.compile(r'^[^\w]+'),                    ''),
]

# Token-level fixes (applied after split, match whole token only)
_TOKEN_FIXES = [
    (re.compile(r'^soda$', re.I), 'baking soda'),
]

# ---------------------------------------------------------------------------
# 2. Known ingredient vocabulary for fuzzy matching
# ---------------------------------------------------------------------------

_KNOWN_INGREDIENTS = [
    "wheat flour", "whole wheat flour", "enriched flour", "unbleached flour",
    "enriched unbleached flour", "refined wheat flour", "oat flour",
    "corn flour", "rice flour", "barley flour", "malted barley flour",
    "corn meal", "cornmeal", "enriched corn meal", "degermed yellow cornmeal",
    "yellow cornmeal", "whole wheat", "wheat bran", "rice bran",
    "soybean oil", "canola oil", "sunflower oil", "palm oil", "palmolein",
    "edible vegetable oil", "vegetable oil", "olive oil", "coconut oil",
    "corn oil", "cottonseed oil",
    "sugar", "brown sugar", "glucose", "dextrose", "fructose", "sucrose",
    "liquid glucose", "corn syrup", "high fructose corn syrup", "invert sugar",
    "honey", "honey powder", "maple syrup",
    "milk", "whole milk", "skim milk", "whey", "whey protein",
    "whey protein concentrate", "cheddar cheese", "cheese",
    "cheese cultures", "cheese seasoning", "cream", "butter", "casein",
    "salt", "sea salt", "iodized salt", "iodised salt", "sodium chloride",
    "baking soda", "sodium bicarbonate", "baking powder",
    "sodium acid pyrophosphate", "cream of tartar", "monocalcium phosphate",
    "niacin", "riboflavin", "thiamin mononitrate", "thiamin hydrochloride",
    "folic acid", "folate", "ascorbic acid", "vitamin a", "vitamin c",
    "reduced iron", "ferrous sulfate",
    "monosodium glutamate", "sodium benzoate", "potassium sorbate",
    "sodium nitrate", "sodium nitrite", "bha", "bht", "tbhq",
    "tartrazine", "yellow 5", "yellow 6", "red 40", "blue 1",
    "carrageenan", "xanthan gum", "guar gum", "lecithin",
    "maltodextrin", "modified starch", "sodium acid pyrophosphate",
    "acetylated distarch adipate", "distarch phosphate",
    "mono and diglycerides", "soy lecithin",
    "disodium guanylate", "disodium inosinate",
    "lactic acid", "citric acid", "acetic acid", "phosphoric acid",
    "natural flavor", "natural flavors", "artificial flavor", "artificial flavors",
    "natural and artificial flavors",
    "soy protein", "whey protein concentrate", "eggs", "egg whites",
    "yeast extract", "malt extract", "cereal extract", "enzymes", "rennet",
    "onion", "chopped onion", "garlic", "ginger", "chillies",
    "tomato", "carrot", "spinach",
    "honey powder", "rolled oats", "oats", "almonds",
    "liquid glucose", "dextrose", "maida",
]

_KNOWN_SET = set(_KNOWN_INGREDIENTS)

try:
    from rapidfuzz import process as rfprocess, fuzz as rffuzz
    _HAS_FUZZ = True
except ImportError:
    _HAS_FUZZ = False

_FUZZY_THRESHOLD = 88
_MIN_TOKEN_LEN   = 4

# ---------------------------------------------------------------------------
# 3. Descriptor phrases to discard
# ---------------------------------------------------------------------------

_DESCRIPTOR_PHRASES = re.compile(
    r"^(?:made\s+from|derived\s+from|contains|and\s*\/\s*or|"
    r"from\s+\w+|processed\s+with|produced\s+from|extracted\s+from|"
    r"blend\s+of|mixture\s+of)\b.*$",
    re.IGNORECASE,
)

_BARE_OIL  = re.compile(r"^(canola|sunflower|soybean|soya|corn|palm|coconut|olive)$", re.I)
_AND_OR    = re.compile(r"^and\s*/\s*or\s+", re.I)
_FAKE_PCT  = re.compile(r'\(\s*\d[\d\s\.]*[0-9]\s*$')

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def correct_ocr_text(text: str) -> str:
    """Apply regex typo fixes to raw OCR text before parsing."""
    for pattern, replacement in _TYPO_FIXES:
        text = pattern.sub(replacement, text)
    return text


def correct_ingredient_token(name: str) -> str:
    """
    Post-parse correction of a single ingredient token.
    Returns corrected name, or '' if the token should be discarded.
    """
    if not name:
        return ""

    # Strip fake percent parens: "oat flour (10.79" -> "oat flour"
    name = _FAKE_PCT.sub("", name).strip()

    # Strip unclosed paren — keep whichever side is more meaningful
    if "(" in name and ")" not in name:
        before = name[:name.index("(")].strip()
        inside = name[name.index("(") + 1:].strip()
        if len(before) >= 2 and re.search(r"[a-zA-Z]{2,}", before):
            name = before
        elif len(inside) >= 2 and re.search(r"[a-zA-Z]{2,}", inside):
            name = inside

    name = re.sub(r"[\(\[\s]+$", "", name).strip()
    name = _AND_OR.sub("", name).strip()

    if _DESCRIPTOR_PHRASES.match(name):
        return ""

    # Apply typo fixes
    for pattern, replacement in _TYPO_FIXES:
        name = pattern.sub(replacement, name)
    # Token-level fixes
    for pattern, replacement in _TOKEN_FIXES:
        name = pattern.sub(replacement, name)

    name = re.sub(r"\s+", " ", name).strip()

    if not name or len(name) < 2:
        return ""

    name_lower = name.lower()

    if name_lower in _KNOWN_SET:
        return name_lower

    if _HAS_FUZZ and len(name) >= _MIN_TOKEN_LEN:
        match = rfprocess.extractOne(
            name_lower,
            _KNOWN_INGREDIENTS,
            scorer=rffuzz.token_sort_ratio,
            score_cutoff=_FUZZY_THRESHOLD,
        )
        if match:
            return match[0]

    return name_lower


def merge_split_tokens(tokens: list) -> list:
    """Fix tokens that should be merged — e.g. bare 'canola' -> 'canola oil'."""
    result = []
    skip_next = False
    for i, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if _BARE_OIL.match(tok):
            if i + 1 < len(tokens) and tokens[i + 1].strip().lower() == "oil":
                result.append(tok + " oil")
                skip_next = True
            else:
                result.append(tok + " oil")
            continue
        result.append(tok)
    return result

"""
modules/ocr_correct.py — Fuzzy OCR error correction for ingredient names.

EasyOCR commonly misreads:
  b <-> h  (barlev -> barley, honev -> honey)
  y <-> v  (sovbean -> soybean, malted barlev -> barley)
  l <-> 1  (whey 1 protein -> whey l protein)
  gh <-> h (pyrophosghate -> pyrophosphate)
  0 <-> o  in words
  { } residue from bracket confusion

Strategy:
  1. Regex-based exact typo fixes for highest-frequency OCR errors
  2. Fuzzy match each token against a known ingredient dictionary
     using rapidfuzz (if installed) — only correct if score >= 88
  3. Remove non-ingredient descriptor phrases ("made from X", "and/or")
  4. Merge "canola" + following "oil" -> "canola oil"
"""

import re

# ---------------------------------------------------------------------------
# 1. Exact regex typo fixes — ordered by frequency of occurrence
# ---------------------------------------------------------------------------

_TYPO_FIXES = [
    # Character-level OCR confusions
    (re.compile(r'\barlev\b', re.I),        'arley'),      # barlev -> barley
    (re.compile(r'\bhonev\b', re.I),        'honey'),       # honev -> honey
    (re.compile(r'\bsovbean\b', re.I),      'soybean'),     # sovbean -> soybean
    (re.compile(r'\bsoyabean\b', re.I),     'soybean'),     # soyabean -> soybean
    (re.compile(r'\bpyrophosghate\b', re.I),'pyrophosphate'),
    (re.compile(r'\bpyrophosphate\b', re.I),'pyrophosphate'),  # normalise
    (re.compile(r'\bwhev\b', re.I),         'whey'),
    (re.compile(r'\bniacm\b', re.I),        'niacin'),
    (re.compile(r'\briboflav[il]n\b', re.I),'riboflavin'),
    (re.compile(r'\bthiamm\b', re.I),       'thiamin'),
    (re.compile(r'\bascorb[il]c\b', re.I),  'ascorbic'),
    (re.compile(r'\bglucouse\b', re.I),     'glucose'),
    (re.compile(r'\bcornmea[il]\b', re.I),  'cornmeal'),
    (re.compile(r'\bflour\b', re.I),        'flour'),       # normalise fIour etc
    (re.compile(r'\bfloiir\b', re.I),       'flour'),
    (re.compile(r'\blod[il]z[eo]d\b', re.I),'iodized'),
    (re.compile(r'\blod[il]s[eo]d\b', re.I),'iodised'),
    (re.compile(r'\bcalc[il]um\b', re.I),   'calcium'),
    (re.compile(r'\bsod[il]um\b', re.I),    'sodium'),
    (re.compile(r'\bpotass[il]um\b', re.I), 'potassium'),
    (re.compile(r'\bmono[s5]od[il]um\b', re.I), 'monosodium'),
    (re.compile(r'\bpalmole[il]n\b', re.I), 'palmolein'),
    (re.compile(r'\bcarotem\b', re.I),      'carotene'),
    (re.compile(r'\btocopheio[il]\b', re.I),'tocopherol'),
    # Number/letter confusion
    (re.compile(r'\bwh[e3]y\b', re.I),      'whey'),
    (re.compile(r'(\bwhey)\s+[1l]\s+(protein\b)', re.I), r'\1 \2'),  # whey 1 protein -> whey protein
    (re.compile(r'\b0il\b'),                'oil'),         # 0il -> oil
    (re.compile(r'\boi[il]\b', re.I),       'oil'),
    # Multi-word merges from paren stripping
    (re.compile(r'\bascorbic\s+acid\s+dough\s+conditioner\b', re.I), 'ascorbic acid'),
    # Bracket/brace residue
    (re.compile(r'[\{\}\[\]\\|]'),          ' '),
    # Stray punctuation at start of token (after leading noise strip)
    (re.compile(r'^[^\w]+'),                ''),
]

# Separate single-token fixes applied AFTER split (not to whole text)
_TOKEN_FIXES = [
    # "soda" alone -> "baking soda" (but "baking soda" stays as-is)
    (re.compile(r'^soda$', re.I), 'baking soda'),
]

# ---------------------------------------------------------------------------
# 2. Known ingredient vocabulary for fuzzy matching
# ---------------------------------------------------------------------------

_KNOWN_INGREDIENTS = [
    # Flours & grains
    "wheat flour", "whole wheat flour", "enriched flour", "unbleached flour",
    "enriched unbleached flour", "refined wheat flour", "oat flour",
    "corn flour", "rice flour", "barley flour", "malted barley flour",
    "corn meal", "cornmeal", "enriched corn meal", "degermed yellow cornmeal",
    "yellow cornmeal", "whole wheat", "wheat bran", "rice bran",
    "soy flour", "tapioca flour", "buckwheat flour",
    # Fats & oils
    "soybean oil", "canola oil", "sunflower oil", "palm oil", "palmolein",
    "edible vegetable oil", "vegetable oil", "olive oil", "coconut oil",
    "corn oil", "cottonseed oil",
    # Sugars
    "sugar", "brown sugar", "powdered sugar", "glucose", "dextrose",
    "fructose", "sucrose", "maltose", "liquid glucose", "corn syrup",
    "high fructose corn syrup", "invert sugar", "honey", "honey powder",
    "maple syrup", "molasses", "treacle",
    # Dairy
    "milk", "whole milk", "skim milk", "whey", "whey protein",
    "whey protein concentrate", "cheddar cheese", "cheese",
    "cheese cultures", "cheese seasoning", "cream", "butter", "casein",
    "buttermilk", "yogurt",
    # Salt
    "salt", "sea salt", "iodized salt", "iodised salt", "sodium chloride",
    # Leavening
    "baking soda", "sodium bicarbonate", "baking powder",
    "sodium acid pyrophosphate", "cream of tartar", "monocalcium phosphate",
    # Vitamins & minerals
    "niacin", "riboflavin", "thiamin mononitrate", "thiamin hydrochloride",
    "folic acid", "folate", "ascorbic acid", "vitamin a", "vitamin c",
    "vitamin d", "vitamin e", "reduced iron", "ferrous sulfate",
    "calcium carbonate", "zinc oxide",
    # Additives
    "monosodium glutamate", "sodium benzoate", "potassium sorbate",
    "sodium nitrate", "sodium nitrite", "bha", "bht", "tbhq",
    "tartrazine", "yellow 5", "yellow 6", "red 40", "blue 1",
    "carrageenan", "xanthan gum", "guar gum", "lecithin",
    "maltodextrin", "modified starch", "sodium acid pyrophosphate",
    "acetylated distarch adipate", "distarch phosphate",
    "mono and diglycerides", "soy lecithin",
    "disodium guanylate", "disodium inosinate",
    "lactic acid", "citric acid", "acetic acid", "phosphoric acid",
    "natural flavor", "natural flavors", "artificial flavor",
    "artificial flavors", "natural and artificial flavors",
    # Proteins & misc
    "soy protein", "whey protein concentrate", "eggs", "egg whites",
    "yeast extract", "malt extract", "cereal extract",
    "enzymes", "rennet",
    # Vegetables
    "onion", "chopped onion", "garlic", "ginger", "chillies",
    "tomato", "carrot", "spinach",
    # Other
    "honey powder", "rolled oats", "oats", "almonds",
    "liquid glucose", "dextrose", "maida",
]

_KNOWN_SET = set(_KNOWN_INGREDIENTS)

# Try to import rapidfuzz for fuzzy matching
try:
    from rapidfuzz import process as rfprocess, fuzz as rffuzz
    _HAS_FUZZ = True
except ImportError:
    _HAS_FUZZ = False

_FUZZY_THRESHOLD = 88   # minimum score (0-100) to accept a fuzzy correction
_MIN_TOKEN_LEN   = 4    # don't fuzzy-match very short tokens (too noisy)


# ---------------------------------------------------------------------------
# 3. Descriptor / non-ingredient phrases to remove
# ---------------------------------------------------------------------------

_DESCRIPTOR_PHRASES = re.compile(
    r"^(?:made\s+from|derived\s+from|contains|and\s*\/\s*or|"
    r"from\s+\w+|processed\s+with|produced\s+from|extracted\s+from|"
    r"blend\s+of|mixture\s+of)\b.*$",
    re.IGNORECASE,
)

# Tokens that are just a single oil type without "oil" — try to reattach
_BARE_OIL = re.compile(r"^(canola|sunflower|soybean|soya|corn|palm|coconut|olive)$", re.I)

# Split "and/or X" into just "X"
_AND_OR = re.compile(r"^and\s*/\s*or\s+", re.I)

# Stray % that EasyOCR reads as a digit (0-9 where % should be)
# e.g. "oat flour (10.79" where 9 = misread %
_FAKE_PERCENT_PAREN = re.compile(r'\(\s*\d[\d\s\.]*[0-9]\s*$')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def correct_ocr_text(text: str) -> str:
    """Apply regex typo fixes to raw OCR text before parsing."""
    for pattern, replacement in _TYPO_FIXES:
        text = pattern.sub(replacement, text)
    return text


def correct_ingredient_token(name: str, context_tokens: list = None) -> str:
    """
    Post-parse correction of a single ingredient token.
    Returns corrected name, or "" if the token should be discarded.
    """
    if not name:
        return ""

    # Strip fake percent parens: "oat flour (10.79" -> "oat flour"
    name = _FAKE_PERCENT_PAREN.sub("", name).strip()

    # Strip unclosed paren: "cheddar cheese (milk" -> "cheddar cheese"
    # If there's an open "(" with no closing ")" and the part before it
    # is a meaningful ingredient name, keep only the part before the paren.
    if "(" in name and ")" not in name:
        before_paren = name[:name.index("(")].strip()
        inside_paren = name[name.index("(") + 1:].strip()
        # If the part before the paren is a real ingredient (has letters, reasonable)
        if len(before_paren) >= 2 and re.search(r"[a-zA-Z]{2,}", before_paren):
            # Use the before-paren content as the name
            name = before_paren
        # Otherwise try the inside
        elif len(inside_paren) >= 2 and re.search(r"[a-zA-Z]{2,}", inside_paren):
            name = inside_paren

    name = re.sub(r"[\(\[\s]+$", "", name).strip()  # trailing open paren/bracket

    # Strip "and/or" prefix
    name = _AND_OR.sub("", name).strip()

    # Discard descriptor phrases
    if _DESCRIPTOR_PHRASES.match(name):
        return ""

    # Apply global typo fixes
    for pattern, replacement in _TYPO_FIXES:
        name = pattern.sub(replacement, name)
    # Apply token-level fixes (only match whole token)
    for pattern, replacement in _TOKEN_FIXES:
        name = pattern.sub(replacement, name)
    name = re.sub(r"\s+", " ", name).strip()

    if not name or len(name) < 2:
        return ""

    # If exact match in known set, done
    if name.lower() in _KNOWN_SET:
        return name.lower()

    # Fuzzy match against known ingredients
    if _HAS_FUZZ and len(name) >= _MIN_TOKEN_LEN:
        match = rfprocess.extractOne(
            name.lower(),
            _KNOWN_INGREDIENTS,
            scorer=rffuzz.token_sort_ratio,
            score_cutoff=_FUZZY_THRESHOLD,
        )
        if match:
            return match[0]

    return name.lower()


def merge_split_tokens(tokens: list) -> list:
    """
    Fix tokens that should be merged or cleaned after initial splitting.
    e.g. ["canola", "oil"] should be ["canola oil"] if "oil" follows "canola"
         ["baking", "soda"] should already be merged (done by line-join)
    Also removes tokens that are just oil type names without "oil".
    """
    result = []
    skip_next = False
    for i, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue

        # Bare oil type: try to see if next token is "oil"
        if _BARE_OIL.match(tok):
            if i + 1 < len(tokens) and tokens[i + 1].strip().lower() == "oil":
                result.append(tok + " oil")
                skip_next = True
                continue
            else:
                # Keep it — might be "canola" as part of "canola oil" on label
                # but score it as canola oil anyway
                result.append(tok + " oil")
                continue

        result.append(tok)
    return result

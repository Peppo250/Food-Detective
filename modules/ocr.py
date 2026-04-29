"""
modules/ocr.py — Image preprocessing and ingredient text extraction.
OCR engine: EasyOCR (pure Python, no binary install needed).
"""

import re
import io
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from modules.ocr_correct import correct_ocr_text, correct_ingredient_token, merge_split_tokens

# ---------------------------------------------------------------------------
# EasyOCR singleton
# ---------------------------------------------------------------------------

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        try:
            import easyocr
        except ImportError:
            raise RuntimeError(
                "EasyOCR is not installed.\n"
                "Run:  pip install easyocr\n"
                "First run downloads ~100 MB of model weights (once only)."
            )
        print("[ocr] Loading EasyOCR model (first run downloads ~100 MB)...")
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        print("[ocr] EasyOCR ready.")
    return _reader


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_ingredients_from_image(image_bytes: bytes) -> list[str]:
    img = _load(image_bytes)
    img = _preprocess(img)
    raw_text = _ocr(img)
    # Apply regex typo fixes to the raw OCR text before parsing
    corrected_text = correct_ocr_text(raw_text)
    tokens = _parse(corrected_text)
    # Post-parse: fuzzy-correct each token, merge split oil names, remove descriptors
    corrected = []
    for tok in tokens:
        fixed = correct_ingredient_token(tok)
        if fixed:
            corrected.append(fixed)
    corrected = merge_split_tokens(corrected)
    # Final dedup (fuzzy correction may have unified some tokens)
    seen = set()
    result = []
    for t in corrected:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------

def _load(image_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def _preprocess(img: Image.Image) -> Image.Image:
    w, h = img.size
    if w < 1200:
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.6)
    img = img.filter(ImageFilter.SHARPEN)
    return img


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def _ocr(img: Image.Image) -> str:
    reader = _get_reader()
    img_np = np.array(img)
    results = reader.readtext(
        img_np, detail=1, paragraph=False, batch_size=8,
        width_ths=0.7, height_ths=0.5, contrast_ths=0.1, adjust_contrast=0.5,
    )
    if not results:
        return ""
    results = [(bbox, text, conf) for bbox, text, conf in results if conf >= 0.20]

    def _sort_key(r):
        bbox = r[0]
        return (round(min(pt[1] for pt in bbox) / 15), min(pt[0] for pt in bbox))

    results.sort(key=_sort_key)
    lines, current_bucket, current_parts = [], None, []
    for bbox, text, conf in results:
        bucket = round(min(pt[1] for pt in bbox) / 15)
        if current_bucket is None:
            current_bucket = bucket
        if bucket == current_bucket:
            current_parts.append(text)
        else:
            lines.append(" ".join(current_parts))
            current_parts = [text]
            current_bucket = bucket
    if current_parts:
        lines.append(" ".join(current_parts))
    return _join_wrapped_lines(lines)


# ---------------------------------------------------------------------------
# Line-wrap joining
# ---------------------------------------------------------------------------

_SECTION_START_RE = re.compile(
    r"^\s*(?:OTHER|INACTIVE|INERT|ACTIVE|TO[A-Z]{2,4}|"
    r"YIELDS?|CONTAINS|NUTRITION|ALLERGEN|WARNING|DIRECTION|"
    r"STORAGE|BEST\s*BEFORE|KEEP\s*OUT|FIRST\s*AID|"
    r"MAY\s+CONTAIN|EPA\s+REG)\b",
    re.IGNORECASE,
)


def _join_wrapped_lines(lines: list) -> str:
    """Merge EasyOCR word-wrapped lines into single lines."""
    if not lines:
        return ""
    result_lines = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        next_line = lines[i + 1] if i + 1 < len(lines) else None
        is_real_break = (
            not line
            or re.search(r'[,;)\]."\']\s*$', line)
            or (next_line and _SECTION_START_RE.match(next_line))
        )
        if not is_real_break and next_line is not None:
            lines[i + 1] = line + " " + lines[i + 1].lstrip()
        else:
            result_lines.append(line)
        i += 1
    return "\n".join(result_lines)


# ---------------------------------------------------------------------------
# INS / E-number decoder
# Translates additive codes to their canonical names before parsing.
# ---------------------------------------------------------------------------

# Map INS/E number -> canonical ingredient name used by the scorer
_INS_NAMES = {
    # Acids / acidity regulators
    "260": "acetic acid", "270": "lactic acid", "330": "citric acid",
    "331": "sodium citrate", "332": "potassium citrate", "333": "calcium citrate",
    "334": "tartaric acid", "336": "potassium tartrate", "338": "phosphoric acid",
    "339": "sodium phosphate", "340": "potassium phosphate",
    # Antioxidants
    "300": "ascorbic acid", "301": "sodium ascorbate", "302": "calcium ascorbate",
    "304": "ascorbyl palmitate",
    "306": "tocopherols", "307": "alpha-tocopherol",
    "310": "propyl gallate", "319": "tbhq", "320": "bha", "321": "bht",
    # Colours
    "100": "curcumin", "101": "riboflavin", "102": "tartrazine",
    "104": "quinoline yellow", "107": "yellow 2g",
    "110": "sunset yellow", "120": "carmine", "122": "azorubine",
    "123": "amaranth", "124": "ponceau 4r", "127": "erythrosine",
    "129": "allura red", "131": "patent blue v", "132": "indigo carmine",
    "133": "brilliant blue", "141": "chlorophylls", "142": "green s",
    "143": "fast green", "150a": "caramel color i", "150b": "caramel color ii",
    "150c": "caramel color iii", "150d": "caramel color iv",
    "151": "brilliant black", "153": "carbon black", "160a": "beta-carotene",
    "160b": "annatto", "162": "beetroot red", "163": "anthocyanins",
    # Preservatives
    "200": "sorbic acid", "201": "sodium sorbate", "202": "potassium sorbate",
    "203": "calcium sorbate",
    "210": "benzoic acid", "211": "sodium benzoate", "212": "potassium benzoate",
    "213": "calcium benzoate", "214": "ethylparaben", "216": "propylparaben",
    "220": "sulfur dioxide", "221": "sodium sulfite", "222": "sodium bisulfite",
    "223": "sodium metabisulfite", "224": "potassium metabisulfite",
    "228": "potassium bisulfite",
    "249": "potassium nitrite", "250": "sodium nitrite",
    "251": "sodium nitrate", "252": "potassium nitrate",
    "280": "propionic acid", "281": "sodium propionate", "282": "calcium propionate",
    "283": "potassium propionate",
    # Emulsifiers / stabilisers
    "322": "lecithin", "400": "alginic acid", "401": "sodium alginate",
    "406": "agar", "407": "carrageenan", "410": "locust bean gum",
    "412": "guar gum", "414": "acacia gum", "415": "xanthan gum",
    "416": "karaya gum", "420": "sorbitol", "421": "mannitol",
    "422": "glycerol", "440": "pectin",
    "450": "diphosphates", "451": "triphosphates", "452": "polyphosphates",
    "460": "cellulose", "461": "methyl cellulose", "466": "carboxymethyl cellulose",
    "471": "mono and diglycerides", "472": "acetic acid esters of mono and diglycerides",
    "476": "polyglycerol polyricinoleate", "477": "propylene glycol esters",
    # Leavening / raising agents
    "500": "sodium carbonate", "500i": "sodium bicarbonate", "500ii": "sodium sesquicarbonate",
    "501": "potassium carbonate", "503": "ammonium carbonate",
    "504": "magnesium carbonate", "507": "hydrochloric acid",
    "516": "calcium sulfate", "524": "sodium hydroxide",
    # Flavour enhancers
    "620": "glutamic acid", "621": "monosodium glutamate",
    "622": "monopotassium glutamate", "623": "calcium glutamate",
    "624": "monoammonium glutamate", "625": "magnesium glutamate",
    "626": "guanylic acid", "627": "disodium guanylate",
    "628": "dipotassium guanylate", "629": "calcium guanylate",
    "630": "inosinic acid", "631": "disodium inosinate",
    "635": "disodium ribonucleotides",
    # Sweeteners
    "420": "sorbitol", "421": "mannitol", "950": "acesulfame potassium",
    "951": "aspartame", "952": "cyclamate", "953": "isomalt",
    "954": "saccharin", "955": "sucralose", "957": "thaumatin",
    "960": "steviol glycosides", "961": "neotame",
    # Thickeners / starches
    "1400": "dextrin", "1401": "acid treated starch", "1402": "alkaline treated starch",
    "1404": "oxidised starch", "1410": "monostarch phosphate",
    "1412": "distarch phosphate", "1413": "phosphated distarch phosphate",
    "1414": "acetylated distarch phosphate", "1420": "starch acetate",
    "1422": "acetylated distarch adipate", "1440": "hydroxypropyl starch",
    "1442": "hydroxypropyl distarch phosphate", "1450": "starch sodium octenyl succinate",
}


def _decode_ins(text: str) -> str:
    """
    Replace INS/E-number codes with their canonical names.
    Handles: INS 500i, INS 320, (INS 211), E211, 150d, etc.
    """
    def _replace(m):
        code = m.group(1).strip().lower()
        return _INS_NAMES.get(code, m.group(0))  # keep original if not found

    # Match: INS 500i, INS500i, E500i, (INS 320), - 211, – 627
    text = re.sub(
        r'\b(?:INS|E)\s*(\d{3,4}[a-z]?(?:\s*[,&]\s*\d{3,4}[a-z]?)*)\b',
        lambda m: ", ".join(
            _INS_NAMES.get(c.strip().lower(), "INS " + c.strip())
            for c in re.split(r'[,&\s]+', m.group(1))
            if c.strip()
        ),
        text, flags=re.IGNORECASE,
    )
    # Match standalone dash-separated codes: "- 211", "– 627 & 631", ": 260, 330"
    text = re.sub(
        r'[-–:]\s*(\d{3,4}[a-z]?)(?:\s*[,&]\s*(\d{3,4}[a-z]?))*',
        lambda m: ": " + ", ".join(
            _INS_NAMES.get(c.strip().lower(), c.strip())
            for c in re.findall(r'\d{3,4}[a-z]?', m.group(0))
        ),
        text, flags=re.IGNORECASE,
    )
    return text


# ---------------------------------------------------------------------------
# Text -> ingredient list parser
# ---------------------------------------------------------------------------

_INGREDIENT_HEADERS = re.compile(
    r"(?:ACTIVE\s+)?INGRED[A-Z]{4,8}S?\s*:?\s*",
    re.IGNORECASE,
)

_HARD_STOP = re.compile(
    r"CONTAINS\s*:\s*(?:ADDED|PERMITTED|GLUTEN|WHEAT|MILK|SOY|NUT|ALMOND)|"
    r"MAY\s+CONTAIN|"
    r"CONTAINS\s+GLUTEN|CONTAINS\s+ADDED|CONTAINS\s+PERMITTED|"
    r"NUTRITION\s*FACTS?|ALLERGEN|"
    r"WARNINGS?|DIRECTIONS?|STORAGE|BEST\s*BEFORE|KEEP\s*OUT|"
    r"FIRST\s*AID|PRECAUTION",
    re.IGNORECASE,
)

_DROP_LINES = re.compile(
    r"^[ \t]*(?:"
    r"(?:OTHER|INACTIVE|INERT)\s+INGRED\w*\s*:?.*"
    r"|TO[A-Z]{2,4}\s*[\.\s]*[\d\.]+"
    r"|YIELDS?\s+[\d\.].*"
    r"|CONTAINS\s+NO\s+\w+"
    r"|EPA\s+REG.*"
    r")[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

_SQUARE_BRACKETS = re.compile(r"\[([^\]]*)\]")
_DOT_LEADERS     = re.compile(r"\.{2,}")

# Strip percentages including those stuck inside parens: "(24%", "4.2%)"
_PERCENTAGE       = re.compile(r"\d+(\.\d+)?\s*%")

_QUANTITY_UNIT    = re.compile(r"\b\d+(\.\d+)?\s*(mg|g|mcg|iu|ml|kg|oz|lb)\b", re.IGNORECASE)
_NUMERIC_ONLY     = re.compile(r"^[\d\s\.\,%\(\)\-\+&]+$")

# Parens that contain ONLY a number or percentage (OCR residue): (24, (9, (4.2
_NUMERIC_PAREN    = re.compile(r"\(\s*\d[\d\s\.,]*\s*\)")

# Parens with function annotations (no comma inside)
_FUNCTION_NOTE = re.compile(
    r"[\(\[]\s*(?!"
    r"[^,\)\]]{0,60},"
    r")"
    r"(?:dough\s+conditioner|preservative|antioxidant|stabilis[eo]r|"
    r"emulsifier|colour|color|flavou?ring|acidity\s+regulator|"
    r"raising\s+agent|humectant|thickener|sweetener|as\s+\w[\w\s]{0,30}|"
    r"from\s+\w+|added\s+for\s+\w+|provides?\s+\w+|"
    r"source\s+of\s+\w+|contains?\s+\w+|yields?|"
    r"available|chlorine|phosphorus|\d+\s*%)"
    r"[^\)\]]*[\)\]]",
    re.IGNORECASE,
)

# Sub-ingredient parens with a comma (real list)
_SUB_PARENS = re.compile(r"[\(\[]\s*([^\)\]]{4,})\s*[\)\]]")

_LEADING_NOISE  = re.compile(r"^[^a-zA-Z0-9]+")
_TRAILING_NOISE = re.compile(r"[^a-zA-Z0-9]+$")

_NON_FOOD_META = re.compile(
    r"(?:per\s+serving|daily\s+value|%\s*dv\b|amount\s+per|calorie|"
    r"total\s+fat|sodium\s*[:,]\s*\d|cholesterol|carbohydrate|protein\s+\d|"
    r"yields?\s+\d|available\s+chlorine|"
    r"keep\s+out|do\s+not|hazard|first\s+aid)",
    re.IGNORECASE,
)

# Structural label words — never ingredient names
_STRUCTURAL = re.compile(
    r"^(?:INGRED\w*|OTHER|INACTIVE|INERT|ACTIVE|"
    r"TO[A-Z]{2,4}|CONTAINS|LEAVENING|"
    r"MAY|MANUFACTURED|DISTRIBUTED|NET\s*WT|"
    r"UNBLEACHED|ENRICHED|DEGERMED|BLEACHED|"
    r"AND|OR)S?\s*:?\s*$",
    re.IGNORECASE,
)

# Allergen debris tokens
_ALLERGEN_DEBRIS = re.compile(
    r"^(?:may|contain|contains|milk|eggs?|soy|soya|nuts?|"
    r"tree\s+nuts?|peanuts?|shellfish|fish|wheat|gluten|sesame|"
    r"celery|mustard|lupin|molluscs?)$",
    re.IGNORECASE,
)

# Token starts with "and " — artifact from sub-ingredient expansion
_LEADING_AND = re.compile(r"^and\s+", re.IGNORECASE)

_HAS_LETTER = re.compile(r"[a-zA-Z]")
MIN_LEN = 2
MAX_LEN = 70


def _parse(raw_text: str) -> list[str]:
    """Extract and normalise ingredient names from OCR text."""
    text = raw_text

    # 1. Find ingredients header
    match = _INGREDIENT_HEADERS.search(text)
    if match:
        text = text[match.end():]

    # 2. Join EasyOCR word-wraps BEFORE anything else
    text = _join_wrapped_lines(text.split("\n"))

    # 3. Hard stop before allergen / other sections
    stop = _HARD_STOP.search(text)
    if stop:
        text = text[: stop.start()]

    # 4. Drop structural noise lines
    text = _DROP_LINES.sub("", text)

    # 5. Decode INS/E-number codes -> canonical names
    text = _decode_ins(text)

    # 6. Normalise square brackets -> parens
    text = _SQUARE_BRACKETS.sub(r"(\1)", text)

    # 7. Strip dot leaders
    text = _DOT_LEADERS.sub(" ", text)

    # 8. Strip percentages (including those inside parens before paren removal)
    text = _PERCENTAGE.sub("", text)

    # 9. Strip numeric-only parens: "(24", "(9)", "(4.2)" residue after % strip
    text = _NUMERIC_PAREN.sub("", text)

    # 10. Remove function annotation parens
    text = _FUNCTION_NOTE.sub("", text)

    # 11. Flatten sub-ingredient parens (contain commas or "and")
    #     Also keep single-item parens when the content has real letters —
    #     this preserves decoded names like (sodium bicarbonate) from INS decode.
    def _expand_sub(m):
        inner = m.group(1).strip()
        # Remove any remaining percentage noise before deciding
        inner_clean = _PERCENTAGE.sub("", inner).strip()
        inner_clean = re.sub(r"^\W+|\W+$", "", inner_clean).strip()
        has_letters = bool(re.search(r"[a-zA-Z]{2,}", inner_clean))
        if "," in inner or re.search(r"\band\b", inner, re.I):
            return ", " + inner
        # Single item: keep if it contains real letters (decoded ingredient name)
        if has_letters and len(inner_clean) >= 2:
            return ", " + inner_clean
        return ""
    text = _SUB_PARENS.sub(_expand_sub, text)

    # 12. Strip quantity units
    text = _QUANTITY_UNIT.sub("", text)

    # 13. Replace newlines with commas
    text = re.sub(r"\n+", ",", text)

    # 13b. Split on " : " introduced by INS decoder
    text = re.sub(r"\s*:\s*", ", ", text)

    # 13c. Convert " - " and " – " dash separators to commas
    #      "Garlic-9%" becomes "Garlic" after % strip but "and Ginger - " needs comma
    text = re.sub(r"\s+[-–]\s+", ", ", text)

    # 14. Split on commas, semicolons, and also ", and " / " and " at list boundaries
    raw_parts = re.split(r"[,;]+", text)

    seen: set = set()
    result: list = []

    for part in raw_parts:
        name = _DOT_LEADERS.sub(" ", part)
        name = _LEADING_NOISE.sub("", name)       # strip non-alpha noise first
        name = _LEADING_AND.sub("", name)          # now strip leading "and "
        name = _TRAILING_NOISE.sub("", name)
        name = re.sub(r"\s+", " ", name).strip()

        # Strip label prefixes inserted by INS decoder or function notes:
        # "Preservative : sodium benzoate" -> "sodium benzoate"
        # "Raising Agent (sodium bicarbonate" -> try to extract the decoded name
        name = _strip_label_prefix(name)

        # Strip unclosed paren residue: "antioxidant (bha" -> "bha"
        name = _strip_unclosed_paren(name)

        if not _HAS_LETTER.search(name):
            continue
        if not (MIN_LEN <= len(name) <= MAX_LEN):
            continue
        if _STRUCTURAL.match(name):
            continue
        if _NON_FOOD_META.search(name):
            continue
        if _NUMERIC_ONLY.match(name):
            continue
        if _ALLERGEN_DEBRIS.match(name):
            continue

        name_lower = name.lower()
        if name_lower not in seen:
            seen.add(name_lower)
            result.append(name_lower)

    return result


# Patterns for stripping label category prefixes and bare category words.
# Matches both "Preservative : sodium benzoate" (has suffix) and bare "Preservative" (no suffix).
_LABEL_PREFIX = re.compile(
    r"^(?:raising\s+agent|antioxidant|preservative|colour|color|"
    r"acidity\s+regulat\w*|stabilis\w+|stabilizer\w*|emulsif\w+|thicken\w+|"
    r"sweetener|humectant|flavou?r\s*enhancer\w*|flavou?ring\w*|"
    r"firming\s+agent|anti.?caking\s+agent|bleaching\s+agent|"
    r"sequestrant|foaming\s+agent|propellant|"
    r"leavening|raising\s+agent)s?\s*[:\(\-\–]?\s*",
    re.IGNORECASE,
)

# Unclosed paren: "word (content" with no closing ) -> extract content
_UNCLOSED_PAREN = re.compile(r"^(.+?)\s*\(([^)]+)$")


def _strip_label_prefix(name: str) -> str:
    """
    Remove label category prefix, keeping the actual ingredient name.
    e.g. "Preservative : sodium benzoate" -> "sodium benzoate"
         "Raising Agent"                  -> "" (bare category word, discard)
    """
    m = _LABEL_PREFIX.match(name)
    if m:
        rest = name[m.end():].strip()
        # If something meaningful follows the prefix, keep that part
        if len(rest) >= 2 and _HAS_LETTER.search(rest):
            return rest
        # Bare category word with nothing after — discard entirely
        return ""
    return name


def _strip_unclosed_paren(name: str) -> str:
    """
    Handle unclosed parens from OCR truncation or line-end:
    'antioxidant (bha'  -> tries prefix strip -> 'bha'
    If the paren content is a known ingredient, return it.
    If no paren, return as-is.
    """
    m = _UNCLOSED_PAREN.match(name)
    if not m:
        return name
    before = m.group(1).strip()
    inside = m.group(2).strip()
    # If inside looks like a real ingredient (has letters, reasonable length)
    if _HAS_LETTER.search(inside) and 2 <= len(inside) <= 50:
        # Prefer the inside content if before is a label category word
        if _LABEL_PREFIX.match(before + " (") or _STRUCTURAL.match(before):
            return inside
        # Otherwise keep both as separate tokens by returning the full name cleaned
        # (the inside will also appear as its own token if the paren was meant to be closed)
    return name

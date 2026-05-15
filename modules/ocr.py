"""
modules/ocr.py — Image preprocessing and ingredient text extraction.
OCR engine: EasyOCR (pure Python, no binary install needed).
"""

import re
import io
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from modules.ocr_correct import correct_ocr_text, correct_ingredient_token, merge_split_tokens

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
    corrected_text = correct_ocr_text(raw_text)
    tokens = _parse(corrected_text)
    corrected = [f for tok in tokens if (f := correct_ingredient_token(tok))]
    corrected = merge_split_tokens(corrected)
    seen, result = set(), []
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
    """
    Preprocessing pipeline for real phone photos of food labels.

    Handles the hardest cases:
      - Curved / cylindrical packaging (local contrast instead of global)
      - Metallic / foil backgrounds with glare (glare masking)
      - Coloured backgrounds — red, orange, silver (work in greyscale)
      - Images already large (no unnecessary upscale)
      - Small/poor quality images (gentle upscale only if needed)
    """
    w, h = img.size

    # ── Step 1: Smart resize ─────────────────────────────────────────────
    # Phone cameras produce 2000–4000px images. EasyOCR slows down hugely
    # above ~2000px with diminishing returns. Downscale oversized images.
    # Only upscale if genuinely small (e.g. cropped thumbnail < 600px).
    MAX_DIM = 2000
    MIN_DIM = 600

    long_side = max(w, h)
    short_side = min(w, h)

    if long_side > MAX_DIM:
        scale = MAX_DIM / long_side
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size
    elif short_side < MIN_DIM:
        scale = MIN_DIM / short_side
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size

    # ── Step 2: Glare / highlight suppression ────────────────────────────
    # Foil and metallic packaging reflects light into blown-out white
    # patches. These look like valid background to OCR but confuse the
    # text detector. Replace very bright pixels with mid-grey.
    arr = np.array(img, dtype=np.float32)
    glare_mask = np.all(arr > 215, axis=2)           # blown-out pixels
    arr[glare_mask] = 175                             # replace with mid-grey
    img = Image.fromarray(arr.astype(np.uint8))

    # ── Step 3: Convert to greyscale ────────────────────────────────────
    # Coloured backgrounds (red/orange/silver) interfere with contrast
    # enhancement in RGB. Work in greyscale from here.
    img = img.convert("L")

    # ── Step 4: Local contrast enhancement (CLAHE substitute) ───────────
    # Standard global contrast fails on curved packaging because the
    # background brightness varies across the image.
    # Unsharp mask with a large radius boosts text relative to local bg.
    blur_radius = max(15, min(w, h) // 25)  # adaptive: ~4% of short side
    blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    arr_g = np.array(img, dtype=np.float32)
    arr_b = np.array(blurred, dtype=np.float32)
    # Unsharp mask: add back the difference between original and blurred
    strength = 2.2
    enhanced = arr_g + strength * (arr_g - arr_b)
    enhanced = np.clip(enhanced, 0, 255).astype(np.uint8)
    img = Image.fromarray(enhanced)

    # ── Step 5: Global contrast + double sharpen ─────────────────────────
    img = ImageEnhance.Contrast(img).enhance(1.8)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)  # second pass for soft/blurry photos

    # ── Step 6: Convert back to RGB for EasyOCR ──────────────────────────
    img = img.convert("RGB")

    return img


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def _ocr(img: Image.Image) -> str:
    reader = _get_reader()
    img_np = np.array(img)
    results = reader.readtext(
        img_np,
        detail=1,
        paragraph=False,
        batch_size=4,           # smaller batches — more stable on real photos
        width_ths=0.8,          # slightly higher: real photos have more spacing
        height_ths=0.5,
        contrast_ths=0.05,      # lower — let EasyOCR see more candidates
        adjust_contrast=0.7,    # let EasyOCR do its own contrast adjustment too
        text_threshold=0.6,     # confidence threshold for text regions
        low_text=0.3,           # low text threshold — catch faint characters
    )
    if not results:
        return ""

    # Lower confidence threshold for real photos — some chars read at 0.3-0.4
    results = [(bbox, text, conf) for bbox, text, conf in results if conf >= 0.15]

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
# ---------------------------------------------------------------------------

_INS_NAMES = {
    "260": "acetic acid", "270": "lactic acid", "330": "citric acid",
    "331": "sodium citrate", "338": "phosphoric acid",
    "300": "ascorbic acid", "301": "sodium ascorbate",
    "306": "tocopherols", "307": "alpha-tocopherol",
    "310": "propyl gallate", "319": "tbhq", "320": "bha", "321": "bht",
    "100": "curcumin", "101": "riboflavin", "102": "tartrazine",
    "110": "sunset yellow", "120": "carmine", "122": "azorubine",
    "123": "amaranth", "124": "ponceau 4r", "127": "erythrosine",
    "129": "allura red", "132": "indigo carmine", "133": "brilliant blue",
    "142": "green s", "143": "fast green",
    "150a": "caramel color i", "150b": "caramel color ii",
    "150c": "caramel color iii", "150d": "caramel color iv",
    "160a": "beta-carotene", "160b": "annatto", "162": "beetroot red",
    "200": "sorbic acid", "202": "potassium sorbate",
    "210": "benzoic acid", "211": "sodium benzoate", "212": "potassium benzoate",
    "220": "sulfur dioxide", "221": "sodium sulfite",
    "223": "sodium metabisulfite",
    "249": "potassium nitrite", "250": "sodium nitrite",
    "251": "sodium nitrate", "252": "potassium nitrate",
    "281": "sodium propionate", "282": "calcium propionate",
    "322": "lecithin", "406": "agar", "407": "carrageenan",
    "410": "locust bean gum", "412": "guar gum", "415": "xanthan gum",
    "440": "pectin", "471": "mono and diglycerides",
    "500": "sodium carbonate", "500i": "sodium bicarbonate",
    "501": "potassium carbonate", "503": "ammonium carbonate",
    "620": "glutamic acid", "621": "monosodium glutamate",
    "627": "disodium guanylate", "631": "disodium inosinate",
    "635": "disodium ribonucleotides",
    "950": "acesulfame potassium", "951": "aspartame",
    "952": "cyclamate", "954": "saccharin", "955": "sucralose",
    "960": "steviol glycosides",
    "1412": "distarch phosphate", "1422": "acetylated distarch adipate",
    "1440": "hydroxypropyl starch", "1442": "hydroxypropyl distarch phosphate",
}


def _decode_ins(text: str) -> str:
    def _replace(m):
        code = m.group(1).strip().lower()
        return _INS_NAMES.get(code, m.group(0))

    text = re.sub(
        r'\b(?:INS|E)\s*(\d{3,4}[a-z]?(?:\s*[,&]\s*\d{3,4}[a-z]?)*)\b',
        lambda m: ", ".join(
            _INS_NAMES.get(c.strip().lower(), "INS " + c.strip())
            for c in re.split(r'[,&\s]+', m.group(1)) if c.strip()
        ),
        text, flags=re.IGNORECASE,
    )
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
# Parser
# ---------------------------------------------------------------------------

_INGREDIENT_HEADERS = re.compile(
    r"(?:ACTIVE\s+)?INGRED[A-Z]{4,8}S?\s*:?\s*", re.IGNORECASE)

_HARD_STOP = re.compile(
    r"CONTAINS\s*:\s*(?:ADDED|PERMITTED|GLUTEN|WHEAT|MILK|SOY|NUT|ALMOND)|"
    r"MAY\s+CONTAIN|CONTAINS\s+GLUTEN|CONTAINS\s+ADDED|CONTAINS\s+PERMITTED|"
    r"NUTRITION\s*FACTS?|ALLERGEN|WARNINGS?|DIRECTIONS?|STORAGE|"
    r"BEST\s*BEFORE|KEEP\s*OUT|FIRST\s*AID|PRECAUTION",
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

_SQUARE_BRACKETS  = re.compile(r"\[([^\]]*)\]")
_DOT_LEADERS      = re.compile(r"\.{2,}")
_PERCENTAGE       = re.compile(r"\d+(\.\d+)?\s*%")
_QUANTITY_UNIT    = re.compile(r"\b\d+(\.\d+)?\s*(mg|g|mcg|iu|ml|kg|oz|lb)\b", re.IGNORECASE)
_NUMERIC_ONLY     = re.compile(r"^[\d\s\.\,%\(\)\-\+&]+$")
_NUMERIC_PAREN    = re.compile(r"\(\s*\d[\d\s\.,]*\s*\)")

_FUNCTION_NOTE = re.compile(
    r"[\(\[]\s*(?![^,\)\]]{0,60},)"
    r"(?:dough\s+conditioner|preservative|antioxidant|stabilis[eo]r|"
    r"emulsif\w+|colour|color|flavou?ring\w*|acidity\s+regulat\w*|"
    r"raising\s+agent|humectant|thickener|sweetener|as\s+\w[\w\s]{0,30}|"
    r"from\s+\w+|added\s+for\s+\w+|provides?\s+\w+|"
    r"source\s+of\s+\w+|contains?\s+\w+|yields?|"
    r"available|chlorine|phosphorus|\d+\s*%)"
    r"[^\)\]]*[\)\]]",
    re.IGNORECASE,
)

_SUB_PARENS     = re.compile(r"[\(\[]\s*([^\)\]]{4,})\s*[\)\]]")
_LEADING_NOISE  = re.compile(r"^[^a-zA-Z0-9]+")
_TRAILING_NOISE = re.compile(r"[^a-zA-Z0-9]+$")
_LEADING_AND    = re.compile(r"^and\s+", re.IGNORECASE)

_NON_FOOD_META = re.compile(
    r"(?:per\s+serving|daily\s+value|%\s*dv\b|amount\s+per|calorie|"
    r"total\s+fat|sodium\s*[:,]\s*\d|cholesterol|carbohydrate|protein\s+\d|"
    r"yields?\s+\d|available\s+chlorine|keep\s+out|do\s+not|hazard|first\s+aid)",
    re.IGNORECASE,
)

_STRUCTURAL = re.compile(
    r"^(?:INGRED\w*|OTHER|INACTIVE|INERT|ACTIVE|TO[A-Z]{2,4}|CONTAINS|"
    r"LEAVENING|MAY|MANUFACTURED|DISTRIBUTED|NET\s*WT|"
    r"UNBLEACHED|ENRICHED|DEGERMED|BLEACHED|AND|OR)S?\s*:?\s*$",
    re.IGNORECASE,
)

_ALLERGEN_DEBRIS = re.compile(
    r"^(?:may|contain|contains|milk|eggs?|soy|soya|nuts?|tree\s+nuts?|"
    r"peanuts?|shellfish|fish|wheat|gluten|sesame|celery|mustard|lupin|molluscs?)$",
    re.IGNORECASE,
)

_LABEL_PREFIX = re.compile(
    r"^(?:raising\s+agent|antioxidant|preservative|colour|color|"
    r"acidity\s+regulat\w*|stabilis\w+|stabilizer\w*|emulsif\w+|thicken\w+|"
    r"sweetener|humectant|flavou?r\s*enhancer\w*|flavou?ring\w*|"
    r"firming\s+agent|anti.?caking\s+agent|bleaching\s+agent|"
    r"sequestrant|foaming\s+agent|propellant|leavening|raising\s+agent)s?\s*[:\(\-\–]?\s*",
    re.IGNORECASE,
)

_UNCLOSED_PAREN = re.compile(r"^(.+?)\s*\(([^)]+)$")
_HAS_LETTER     = re.compile(r"[a-zA-Z]")
MIN_LEN, MAX_LEN = 2, 70


def _strip_label_prefix(name: str) -> str:
    m = _LABEL_PREFIX.match(name)
    if m:
        rest = name[m.end():].strip()
        if len(rest) >= 2 and _HAS_LETTER.search(rest):
            return rest
        return ""
    return name


def _strip_unclosed_paren(name: str) -> str:
    m = _UNCLOSED_PAREN.match(name)
    if not m:
        return name
    before = m.group(1).strip()
    inside = m.group(2).strip()
    if _HAS_LETTER.search(inside) and 2 <= len(inside) <= 50:
        if _LABEL_PREFIX.match(before + " (") or _STRUCTURAL.match(before):
            return inside
    return name


def _parse(raw_text: str) -> list[str]:
    text = raw_text

    match = _INGREDIENT_HEADERS.search(text)
    if match:
        text = text[match.end():]

    text = _join_wrapped_lines(text.split("\n"))

    stop = _HARD_STOP.search(text)
    if stop:
        text = text[: stop.start()]

    text = _DROP_LINES.sub("", text)
    text = _decode_ins(text)
    text = _SQUARE_BRACKETS.sub(r"(\1)", text)
    text = _DOT_LEADERS.sub(" ", text)
    text = _PERCENTAGE.sub("", text)
    text = _NUMERIC_PAREN.sub("", text)
    text = _FUNCTION_NOTE.sub("", text)

    def _expand_sub(m):
        inner = m.group(1).strip()
        inner_clean = _PERCENTAGE.sub("", inner).strip()
        inner_clean = re.sub(r"^\W+|\W+$", "", inner_clean).strip()
        has_letters = bool(re.search(r"[a-zA-Z]{2,}", inner_clean))
        if "," in inner or re.search(r"\band\b", inner, re.I):
            return ", " + inner
        if has_letters and len(inner_clean) >= 2:
            return ", " + inner_clean
        return ""

    text = _SUB_PARENS.sub(_expand_sub, text)
    text = _QUANTITY_UNIT.sub("", text)
    text = re.sub(r"\n+", ",", text)
    text = re.sub(r"\s*:\s*", ", ", text)
    text = re.sub(r"\s+[-–]\s+", ", ", text)

    raw_parts = re.split(r"[,;]+", text)
    seen: set = set()
    result: list = []

    for part in raw_parts:
        name = _DOT_LEADERS.sub(" ", part)
        name = _LEADING_NOISE.sub("", name)
        name = _LEADING_AND.sub("", name)
        name = _TRAILING_NOISE.sub("", name)
        name = re.sub(r"\s+", " ", name).strip()
        name = _strip_label_prefix(name)
        name = _strip_unclosed_paren(name)

        if not _HAS_LETTER.search(name): continue
        if not (MIN_LEN <= len(name) <= MAX_LEN): continue
        if _STRUCTURAL.match(name): continue
        if _NON_FOOD_META.search(name): continue
        if _NUMERIC_ONLY.match(name): continue
        if _ALLERGEN_DEBRIS.match(name): continue

        name_lower = name.lower()
        if name_lower not in seen:
            seen.add(name_lower)
            result.append(name_lower)

    return result

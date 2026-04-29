"""
modules/scorer.py — Rule-based safety classification for ingredients.

Returns one of: "safe" | "caution" | "avoid" | "toxic" | "unknown"

Priority order (first match wins):
  0. NON_FOOD / TOXIC list  — cleaning chemicals, bleach, industrial compounds
  1. Hardcoded AVOID list   — known harmful food additives for children
  2. Hardcoded CAUTION list — moderately concerning ingredients
  3. API signals            — FDA adverse events, Wikidata hazard flags
  4. Hardcoded SAFE list    — clearly natural/benign ingredients
  5. "unknown"              — not enough data
"""

import re

# ---------------------------------------------------------------------------
# NON-FOOD / TOXIC — cleaning agents, industrial chemicals, not food
# ---------------------------------------------------------------------------
# These should never appear in food. If detected, show a strong warning
# that this is NOT a food product.

NON_FOOD = {
    # Bleach / disinfectants
    "sodium hypochlorite", "hypochlorite", "calcium hypochlorite",
    "bleach", "chlorine bleach",
    # Detergents & surfactants
    "sodium lauryl sulfate", "sodium laureth sulfate", "sls", "sles",
    "linear alkylbenzene sulfonate", "las",
    "alkyl polyglucoside", "cocamidopropyl betaine",
    "sodium dodecylbenzenesulfonate",
    # Disinfectants
    "benzalkonium chloride", "quaternary ammonium",
    "hydrogen peroxide", "isopropyl alcohol", "ethanol",
    "ammonium hydroxide", "ammonia",
    # Industrial / cleaning
    "sodium hydroxide", "potassium hydroxide", "lye",
    "hydrochloric acid", "sulfuric acid", "phosphoric acid",
    "trisodium phosphate", "tsp",
    "sodium carbonate", "washing soda",
    "borax", "sodium tetraborate",
    "acetone", "methanol", "butanol",
    "formaldehyde", "glutaraldehyde",
    "sodium silicate", "silicic acid",
    "optical brightener",
    # Pesticides / herbicides (sometimes on produce labels)
    "glyphosate", "chlorpyrifos", "malathion",
}

# ---------------------------------------------------------------------------
# Hardcoded lists — researched against EU & US child health guidelines
# ---------------------------------------------------------------------------

AVOID = {
    # Artificial colours (EU hyperactivity warning)
    "red 40", "allura red", "e129", "ins 129",
    "yellow 5", "tartrazine", "e102", "ins 102",
    "yellow 6", "sunset yellow", "e110", "ins 110",
    "blue 1", "brilliant blue", "e133", "ins 133",
    "blue 2", "indigo carmine", "e132", "ins 132",
    "green 3", "fast green", "e143", "ins 143",
    "red 3", "erythrosine", "e127", "ins 127",
    "caramel color iv", "caramel colour iv", "e150d", "ins 150d",
    "quinoline yellow", "e104",
    "ponceau 4r", "e124",
    "amaranth", "e123",
    "azorubine", "e122",
    "patent blue v", "e131",
    # Generic "artificial color/colour" — unspecified synthetic dye
    "artificial color", "artificial colour",
    "artificial colors", "artificial colours",
    "fd&c", "fdc color", "fdc colour",
    # Preservatives
    "sodium benzoate", "e211", "ins 211",
    "potassium benzoate", "e212", "ins 212",
    "calcium benzoate", "e213", "ins 213",
    "bha", "butylated hydroxyanisole", "e320", "ins 320",
    "bht", "butylated hydroxytoluene", "e321", "ins 321",
    "tbhq", "tertiary butylhydroquinone", "e319", "ins 319",
    "propyl gallate", "e310", "ins 310",
    "sodium nitrate", "e251", "ins 251",
    "sodium nitrite", "e250", "ins 250",
    "potassium nitrate", "e252", "ins 252",
    "potassium nitrite", "e249", "ins 249",
    "sulfur dioxide", "sulphur dioxide", "e220", "ins 220",
    "sodium sulfite", "sodium sulphite", "e221", "ins 221",
    "sodium metabisulfite", "e223", "ins 223",
    "ethylparaben", "e214", "ins 214",
    "propylparaben", "e216", "ins 216",
    # Artificial sweeteners
    "aspartame", "e951", "ins 951",
    "saccharin", "e954", "ins 954",
    "acesulfame potassium", "acesulfame-k", "e950", "ins 950",
    "cyclamate", "e952", "ins 952",
    "neotame", "e961", "ins 961",
    # Trans fats
    "partially hydrogenated", "hydrogenated vegetable oil", "hydrogenated fat",
    # Glutamates
    "monosodium glutamate", "msg", "e621", "ins 621",
    # High sugar
    "high fructose corn syrup", "hfcs",
    # Other
    "carrageenan", "e407", "ins 407",
    "brominated vegetable oil", "bvo",
    "potassium bromate",
}

CAUTION = {
    # Sugars
    "sugar", "cane sugar", "raw sugar", "brown sugar",
    "invert sugar", "glucose", "glucose syrup", "dextrose",
    "fructose", "maltose", "sucrose", "treacle", "molasses",
    "liquid glucose", "corn syrup", "golden syrup",
    "candied", "candied cranberry", "candied fruit",
    "candied fruit and nut",
    # Refined / processed flours
    "refined flour", "white flour", "enriched flour",
    "bleached flour", "maida", "refined wheat flour",
    # Salt
    "salt", "sodium chloride", "sea salt", "iodized salt", "iodised salt",
    "lodized salt", "lodised salt",          # common OCR/spelling variants
    # Fats
    "palm oil", "palm kernel oil", "palmolein", "edible vegetable oil",
    "refined vegetable oil", "vegetable oil", "shortening",
    # Flavourings (artificial or mixed)
    "artificial flavors", "artificial flavours",
    "artificial flavor", "artificial flavour",
    "natural and artificial flavors", "natural and artificial flavours",
    "nature identical flavour", "nature identical flavor",
    # Starches
    "modified starch", "modified corn starch", "modified food starch",
    "maltodextrin", "acetylated distarch adipate",
    "hydroxypropyl distarch phosphate", "distarch phosphate",
    # Emulsifiers
    "lecithin", "soy lecithin", "sunflower lecithin",
    "mono and diglycerides", "monoglycerides", "diglycerides", "e471",
    "polyglycerol polyricinoleate", "pgpr",
    # Flavour enhancers (with full names from INS decoder)
    "disodium guanylate", "ins 627", "e627",
    "disodium inosinate", "ins 631", "e631",
    "disodium ribonucleotides", "ins 635", "e635",
    "yeast extract",
    # Acidity regulators (generally safe but worth noting)
    "acetic acid", "lactic acid", "citric acid", "phosphoric acid",
    "acidity regulators",
    # Stabilisers
    "xanthan gum", "guar gum", "carboxymethyl cellulose",
    "sodium alginate",
    # Caffeine sources
    "caffeine", "guarana",
    # Misc processed
    "soya sauce", "soy sauce",
    "cereal extract",
    "corn flour",          # fine, but mild processing
    "caramel color i", "caramel color ii", "caramel color iii",
    "caramel colour i", "caramel colour ii", "caramel colour iii",
}

SAFE = {
    # Whole grains & flours
    "rolled oats", "oats", "oat flour", "whole oats",
    "whole wheat", "whole wheat flour", "wheat bran", "wheat flour",
    "whole grain", "barley", "barley flour", "rye",
    "quinoa", "millet", "buckwheat", "rice", "rice flour",
    "corn flour", "corn meal", "cornmeal", "enriched corn meal",
    "degermed yellow cornmeal", "yellow cornmeal",
    "enriched unbleached flour", "unbleached flour", "bread flour",
    "malted barley flour",
    # Leavening
    "baking soda", "sodium bicarbonate", "baking powder",
    "sodium acid pyrophosphate", "cream of tartar",
    "monocalcium phosphate", "raising agent",
    "ammonium carbonate", "sodium carbonate",
    # Vitamins & minerals
    "vitamins", "minerals", "vitamin blend", "mineral blend",
    "vitamin a", "vitamin c", "vitamin d", "vitamin e",
    "vitamin b", "vitamin b6", "vitamin b12",
    "niacin", "riboflavin", "thiamine", "thiamin mononitrate",
    "thiamin hydrochloride", "folic acid", "folate",
    "calcium", "iron", "zinc", "magnesium", "potassium", "phosphorus",
    "reduced iron", "ferrous sulfate",
    "ascorbic acid", "dough conditioner",
    # Dairy & cheese
    "milk", "whole milk", "skim milk", "cream", "butter", "cheese",
    "cheddar", "cheddar cheese", "mozzarella", "yogurt", "whey",
    "whey protein", "whey protein concentrate", "casein",
    "buttermilk", "milk powder", "dried milk", "nonfat dry milk",
    "cheese cultures", "cheese seasoning", "rennet", "enzymes",
    # Eggs
    "eggs", "egg", "egg whites", "egg yolks", "whole eggs",
    # Natural sweeteners
    "honey", "honey powder", "maple syrup", "agave",
    "date syrup", "coconut sugar", "stevia", "steviol glycosides",
    # Fruits & vegetables
    "apple", "banana", "strawberry", "blueberry", "raspberry", "cherry",
    "cranberry", "candied cranberry",
    "tomato", "carrot", "spinach", "onion", "chopped onion", "garlic",
    "ginger", "chilli", "chillies", "chili", "red chilli", "dried red chilli",
    "red chilli powder", "chilli powder",
    "beet", "lemon", "orange", "lime", "grape", "pineapple", "mango",
    "potato", "sweet potato", "vegetables", "corn",
    # Spices & herbs
    "cinnamon", "vanilla", "vanilla extract", "turmeric", "paprika",
    "cumin", "coriander", "pepper", "black pepper", "oregano",
    "basil", "thyme", "rosemary", "mint", "parsley",
    "spices", "spices and condiments", "spices & condiments", "condiments",
    # Nuts & seeds
    "almonds", "walnuts", "cashews", "pecans", "hazelnuts",
    "sunflower seeds", "pumpkin seeds", "chia seeds", "flaxseeds",
    "sesame seeds", "tahini",
    # Proteins & legumes
    "peanuts", "peanut butter", "lentils", "chickpeas", "beans",
    "soy", "tofu", "tempeh", "soy protein",
    # Oils
    "olive oil", "extra virgin olive oil", "coconut oil", "avocado oil",
    "soybean oil", "soyabean oil", "canola oil", "sunflower oil",
    "edible vegetable oil", "corn oil",
    # Flavours
    "natural flavor", "natural flavors", "natural flavour", "natural flavours",
    # Other benign
    "water", "yeast", "vinegar", "apple cider vinegar", "lemon juice",
    "cocoa", "cocoa powder", "dark chocolate", "vanilla bean",
    "gelatin", "pectin", "agar", "corn starch", "tapioca starch",
    "annatto", "beta-carotene", "curcumin", "carmine",
    "locust bean gum", "acacia gum",
    "sorbitol", "mannitol", "glycerol",
    "tocopherols", "alpha-tocopherol",
    "potassium sorbate", "sorbic acid",
    "sodium propionate", "calcium propionate",
    "citric acid", "lactic acid", "acetic acid",
    "cereal extract", "malt extract", "yeast extract",
}


# ---------------------------------------------------------------------------
# Scoring function
# ---------------------------------------------------------------------------

def score_ingredient(data: dict) -> str:
    """
    Classify a single ingredient given its enriched data dict.
    Returns "safe" | "caution" | "avoid" | "toxic" | "unknown".
    """
    name = data.get("name", "").lower().strip()

    # 0. Non-food / toxic chemicals — strongest signal
    if _matches_any(name, NON_FOOD):
        return "toxic"

    # 1. Check AVOID list (exact match or substring)
    if _matches_any(name, AVOID):
        return "avoid"

    # Check E-number directly
    e_num = data.get("e_number", "").lower()
    if e_num and _matches_any(e_num, AVOID):
        return "avoid"

    # FDA adverse events — high count is a red flag
    if data.get("fda_adverse_events", 0) > 500:
        return "avoid"

    # Wikidata hazard flag
    if data.get("wikidata_hazard"):
        return "caution"

    # 2. Check CAUTION list
    if _matches_any(name, CAUTION):
        return "caution"

    # Palm oil is always caution
    if data.get("palm_oil"):
        return "caution"

    # Non-vegan processed additives tend to be caution
    if data.get("in_additive_list") and data.get("non_vegan"):
        return "caution"

    # 3. Check SAFE list
    if _matches_any(name, SAFE):
        return "safe"

    # GRAS confirmed by FDA → safe
    if data.get("fda_gras") is True:
        return "safe"

    # Vegan + in OFF database + no adverse events → probably safe
    if data.get("vegan") and data.get("fda_adverse_events", 0) == 0:
        return "safe"

    return "unknown"


def overall_score(statuses: list[str]) -> str:
    """Compute overall product score from a list of ingredient statuses."""
    if not statuses:
        return "ok"
    toxic_count  = statuses.count("toxic")
    avoid_count  = statuses.count("avoid")
    caution_count = statuses.count("caution")
    total = len(statuses)

    if toxic_count > 0:
        return "not_food"
    if avoid_count >= 2 or (avoid_count == 1 and avoid_count / total > 0.1):
        return "bad"
    if avoid_count == 1 or caution_count / total > 0.3:
        return "ok"
    return "great"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _matches_any(name: str, word_set: set) -> bool:
    """
    True if name matches any entry in word_set.

    Matching rules (in order):
    1. Exact match: "msg" == "msg"
    2. Name STARTS WITH entry + space: "sodium benzoate" starts with "sodium benzoate"
    3. Entry is a WHOLE WORD inside name using word boundaries.
       "bleach" does NOT match "unbleached" (no word boundary before 'b').
       "soda" does NOT match "baking soda" if "baking soda" is a separate entry.
    4. Name is wholly contained IN entry (name is a prefix abbreviation).
    """
    if name in word_set:
        return True
    for entry in word_set:
        if name == entry:
            return True
        # Word-boundary match: entry must appear as a complete token in name
        if re.search(r'(?<![a-z])' + re.escape(entry) + r'(?![a-z])', name):
            return True
        # name wholly inside entry (short abbreviation case)
        if len(name) >= 3 and name in entry and entry.startswith(name):
            return True
    return False

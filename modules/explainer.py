"""
modules/explainer.py — Generate child-friendly explanations (ages 6-12).
"""
import re

_KNOWN = {
    "red 40":    ("Red 40 is a fake red colour made in a lab from oil.",
                  "Some kids feel more hyper or restless after eating it."),
    "allura red":("Allura Red (also called Red 40) is an artificial food dye.",
                  "Studies show it can make some children harder to sit still."),
    "yellow 5":  ("Yellow 5 is a bright yellow dye made from chemicals.",
                  "It can cause allergic reactions and make some kids more hyper."),
    "tartrazine":("Tartrazine is another name for Yellow 5.",
                  "In Europe, foods with it must have a warning label for children!"),
    "yellow 6":  ("Yellow 6 is an orange-yellow artificial colour.",
                  "It can trigger allergies and may affect how some kids behave."),
    "blue 1":    ("Blue 1 is a bright blue dye made from coal tar or oil.",
                  "It can cause allergic reactions in some people."),
    "red 3":     ("Red 3 is a cherry-red artificial dye.",
                  "The USA banned it in cosmetics but it's still in some foods."),
    "sodium benzoate": ("Sodium benzoate is a preservative that stops food going bad.",
                        "When mixed with Vitamin C, it can form a harmful chemical called benzene."),
    "bha":       ("BHA is a chemical preservative used to stop fats from going rotten.",
                  "Some scientists think it might cause cancer if eaten a lot over time."),
    "bht":       ("BHT is similar to BHA — it keeps fats from going bad.",
                  "Some animal studies have found it can cause health problems."),
    "tbhq":      ("TBHQ is a preservative found in many snack foods and fast food.",
                  "Too much has been linked to health problems in animal studies."),
    "sodium nitrate": ("Sodium nitrate is added to meat to keep its pink colour.",
                       "Inside your body it can turn into chemicals that aren't healthy."),
    "sodium nitrite": ("Sodium nitrite preserves meat and gives it a pink look.",
                       "It can form unhealthy chemicals in your body."),
    "aspartame": ("Aspartame is an artificial sweetener used instead of sugar.",
                  "Many scientists debate whether it is completely safe."),
    "saccharin": ("Saccharin was one of the first artificial sweeteners ever made.",
                  "It used to have a cancer warning label — many people still avoid it."),
    "acesulfame potassium": ("Acesulfame-K is a zero-calorie artificial sweetener.",
                             "We don't have many studies on how it affects children."),
    "acesulfame-k": ("Acesulfame-K is a zero-calorie artificial sweetener.",
                     "We don't have many studies on how it affects children."),
    "monosodium glutamate": ("MSG makes food taste more savoury and strong.",
                             "Some kids get headaches or upset stomachs from eating too much."),
    "msg":       ("MSG makes food taste more savoury — like the flavour is turned up.",
                  "Some kids get headaches or upset stomachs from too much of it."),
    "high fructose corn syrup": ("High fructose corn syrup is a very sweet liquid made from corn.",
                                 "It's in many soft drinks and snacks and is linked to weight gain."),
    "hfcs":      ("HFCS is short for high fructose corn syrup — very sweet liquid from corn.",
                  "Eating too much is linked to obesity, diabetes, and tooth decay."),
    "partially hydrogenated": ("This means the fat has been chemically changed to last longer.",
                               "These trans fats are bad for your heart — most countries have banned them!"),
    "hydrogenated vegetable oil": ("Hydrogenated oil is vegetable oil processed to become solid.",
                                   "It creates trans fats, which are really bad for your heart."),
    "carrageenan": ("Carrageenan is extracted from red seaweed and used to thicken foods.",
                    "Some scientists think it can irritate our gut and cause inflammation."),
    "artificial color":  ("Artificial color is a synthetic dye added to make food look brighter.",
                          "Many artificial colors have been linked to hyperactivity in children."),
    "artificial colour": ("Artificial colour is a synthetic dye added to make food look brighter.",
                          "Many artificial colours have been linked to hyperactivity in children."),
    "sodium hypochlorite": ("Sodium hypochlorite is the main ingredient in bleach.",
                            "This is a cleaning chemical — NOT food! Do not eat this product!"),
    "hydrogen peroxide": ("Hydrogen peroxide is a strong disinfectant and cleaning agent.",
                          "This is NOT food! It is dangerous to swallow."),
}

_AVOID_TEMPLATE = "{name} is added to food to {purpose}. It's best for kids to avoid it because {concern}."
_CAUTION_TEMPLATE = "{name} is {what}. It's okay in small amounts, but too much {concern}."
_SAFE_TEMPLATE = "{name} is {what}. This is a natural ingredient that gives your body {benefit}!"
_UNKNOWN_TEMPLATE = "We found {name} in this product. We couldn't find enough information about it right now."

_PURPOSES = {
    "colour": "add colour", "color": "add colour", "preserve": "make it last longer",
    "sweet": "make it sweeter", "flavor": "boost the flavour", "flavour": "boost the flavour",
}
_CONCERN_AVOID = "it can affect behaviour, cause allergies, or has been linked to health problems"
_CONCERN_CAUTION = "can add up to more sugar, salt, or fat than is good for you"
_HAS_LETTER = re.compile(r"[a-zA-Z]")


def make_kid_explanation(name: str, status: str, data: dict) -> str:
    if status == "toxic":
        return (f"{name.title()} is a cleaning chemical, NOT a food ingredient. "
                "This product is NOT safe to eat!")

    key = name.lower().strip()
    for known_key, (s1, s2) in _KNOWN.items():
        if known_key in key or key in known_key:
            return s1 + " " + s2

    wiki = data.get("summary", "")
    if wiki and len(wiki) < 280:
        simplified = _simplify(wiki)
        if simplified:
            if status == "avoid":
                return simplified + " It's best for children to avoid this ingredient."
            elif status == "caution":
                return simplified + " It's okay in small amounts, but watch out for too much."
            elif status == "safe":
                return simplified + " This is generally a good, natural ingredient!"

    if status == "avoid":
        return _AVOID_TEMPLATE.format(
            name=name.title(),
            purpose=_guess_purpose(name),
            concern=_CONCERN_AVOID)
    elif status == "caution":
        return _CAUTION_TEMPLATE.format(
            name=name.title(),
            what=_guess_what(name, data),
            concern=_CONCERN_CAUTION)
    elif status == "safe":
        return _SAFE_TEMPLATE.format(
            name=name.title(),
            what=_guess_what(name, data),
            benefit=_guess_benefit(name))
    return _UNKNOWN_TEMPLATE.format(name=name.title())


def _simplify(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    result = sentences[0] if sentences else text
    replacements = [
        (r"\bsynthetic\b", "man-made"), (r"\bsynthesized\b", "made in a lab"),
        (r"\bcompound\b", "chemical"),  (r"\bsubstance\b", "ingredient"),
        (r"\bconsumed\b", "eaten"),     (r"\bderived from\b", "made from"),
    ]
    for pat, rep in replacements:
        result = re.sub(pat, rep, result, flags=re.IGNORECASE)
    return result[:200].strip() if len(result) > 200 else result.strip()


def _guess_purpose(name):
    nl = name.lower()
    for k, v in _PURPOSES.items():
        if k in nl: return v
    return "improve taste or appearance"


def _guess_what(name, data):
    nl = name.lower()
    if any(w in nl for w in ["sugar","syrup","glucose","fructose","dextrose"]): return "a type of sugar"
    if any(w in nl for w in ["oil","fat"]): return "a type of fat or oil"
    if any(w in nl for w in ["salt","sodium"]): return "a type of salt"
    if any(w in nl for w in ["starch","flour"]): return "a starchy ingredient"
    if data.get("e_number"): return f"a food additive ({data['e_number']})"
    return "an ingredient"


def _guess_benefit(name):
    nl = name.lower()
    if any(w in nl for w in ["vitamin","mineral","calcium","iron","zinc","niacin","riboflavin","folic"]):
        return "important vitamins and minerals"
    if any(w in nl for w in ["protein","egg","milk","whey"]): return "protein to help you grow strong"
    if any(w in nl for w in ["fibre","fiber","grain","oat","wheat"]): return "fibre to keep your tummy happy"
    if any(w in nl for w in ["fruit","vegetable","berry","apple","carrot"]): return "natural vitamins from plants"
    return "good nutrition"

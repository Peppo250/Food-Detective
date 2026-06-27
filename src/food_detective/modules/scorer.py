"""
modules/scorer.py — Rule-based safety classifier.
Returns: "safe" | "caution" | "avoid" | "toxic" | "unknown"
"""
import re

NON_FOOD = {
    "sodium hypochlorite","hypochlorite","calcium hypochlorite","bleach",
    "sodium lauryl sulfate","sodium laureth sulfate","sls","sles",
    "benzalkonium chloride","quaternary ammonium",
    "hydrogen peroxide","isopropyl alcohol",
    "ammonium hydroxide","ammonia",
    "sodium hydroxide","potassium hydroxide","lye",
    "hydrochloric acid","sulfuric acid","phosphoric acid",
    "trisodium phosphate","sodium carbonate","washing soda",
    "borax","sodium tetraborate",
    "acetone","methanol","formaldehyde","glutaraldehyde",
    "optical brightener","glyphosate","chlorpyrifos",
}

AVOID = {
    # Artificial colours
    "red 40","allura red","e129","ins 129",
    "yellow 5","tartrazine","e102","ins 102",
    "yellow 6","sunset yellow","e110","ins 110",
    "blue 1","brilliant blue","e133","ins 133",
    "blue 2","indigo carmine","e132","ins 132",
    "green 3","fast green","e143","ins 143",
    "red 3","erythrosine","e127","ins 127",
    "caramel color iv","caramel colour iv","e150d","ins 150d",
    "quinoline yellow","e104","ponceau 4r","e124",
    "amaranth","e123","azorubine","e122","patent blue v","e131",
    "artificial color","artificial colour","artificial colors","artificial colours",
    "fd&c","fdc color","fdc colour",
    # Preservatives
    "sodium benzoate","e211","ins 211",
    "potassium benzoate","e212","ins 212",
    "calcium benzoate","e213","ins 213",
    "bha","butylated hydroxyanisole","e320","ins 320",
    "bht","butylated hydroxytoluene","e321","ins 321",
    "tbhq","tertiary butylhydroquinone","e319","ins 319",
    "propyl gallate","e310","ins 310",
    "sodium nitrate","e251","ins 251",
    "sodium nitrite","e250","ins 250",
    "potassium nitrate","e252","ins 252",
    "potassium nitrite","e249","ins 249",
    "sulfur dioxide","sulphur dioxide","e220","ins 220",
    "sodium sulfite","sodium sulphite","e221","ins 221",
    "sodium metabisulfite","e223","ins 223",
    "ethylparaben","e214","ins 214",
    "propylparaben","e216","ins 216",
    # Sweeteners
    "aspartame","e951","ins 951",
    "saccharin","e954","ins 954",
    "acesulfame potassium","acesulfame-k","e950","ins 950",
    "cyclamate","e952","ins 952",
    "neotame","e961","ins 961",
    # Trans fats
    "partially hydrogenated","hydrogenated vegetable oil","hydrogenated fat",
    # Glutamates
    "monosodium glutamate","msg","e621","ins 621",
    # High sugar
    "high fructose corn syrup","hfcs",
    # Other
    "carrageenan","e407","ins 407",
    "brominated vegetable oil","bvo",
    "potassium bromate",
}

CAUTION = {
    # Sugars
    "sugar","cane sugar","raw sugar","brown sugar",
    "invert sugar","glucose","glucose syrup","dextrose",
    "fructose","maltose","sucrose","treacle","molasses",
    "liquid glucose","corn syrup","golden syrup",
    "candied","candied cranberry","candied fruit","candied fruit and nut",
    # Refined flours
    "refined flour","white flour","bleached flour","maida","refined wheat flour",
    # Salt
    "salt","sodium chloride","sea salt","iodized salt","iodised salt",
    "lodized salt","lodised salt",
    # Fats
    "palm oil","palm kernel oil","palmolein","edible vegetable oil",
    "refined vegetable oil","vegetable oil","shortening",
    # Artificial flavourings
    "artificial flavors","artificial flavours","artificial flavor","artificial flavour",
    "natural and artificial flavors","natural and artificial flavours",
    "nature identical flavour","nature identical flavor",
    # Modified starches
    "modified starch","modified corn starch","modified food starch",
    "maltodextrin","acetylated distarch adipate",
    "hydroxypropyl distarch phosphate","distarch phosphate",
    # Emulsifiers
    "lecithin","soy lecithin","sunflower lecithin",
    "mono and diglycerides","monoglycerides","diglycerides","e471",
    "polyglycerol polyricinoleate","pgpr",
    # Flavour enhancers
    "disodium guanylate","ins 627","e627",
    "disodium inosinate","ins 631","e631",
    "disodium ribonucleotides","ins 635","e635",
    # Acidity regulators
    "acidity regulators","xanthan gum","guar gum",
    "sodium alginate","carboxymethyl cellulose",
    # Misc
    "soya sauce","soy sauce","yeast extract",
    "corn flour","cereal extract",
    "caramel color i","caramel color ii","caramel color iii",
    "caramel colour i","caramel colour ii","caramel colour iii",
    "caffeine","guarana",
}

SAFE = {
    # Whole grains & flours
    "rolled oats","oats","oat flour","whole oats",
    "whole wheat","whole wheat flour","wheat bran","wheat flour",
    "whole grain","barley","barley flour","rye",
    "quinoa","millet","buckwheat","rice","rice flour",
    "corn flour","corn meal","cornmeal","enriched corn meal",
    "degermed yellow cornmeal","yellow cornmeal",
    "enriched unbleached flour","unbleached flour","bread flour",
    "malted barley flour","enriched flour",
    # Leavening
    "baking soda","sodium bicarbonate","baking powder",
    "sodium acid pyrophosphate","cream of tartar",
    "monocalcium phosphate","raising agent",
    "ammonium carbonate","sodium carbonate",
    # Vitamins & minerals
    "vitamins","minerals","vitamin blend","mineral blend",
    "vitamin a","vitamin c","vitamin d","vitamin e",
    "vitamin b","vitamin b6","vitamin b12",
    "niacin","riboflavin","thiamine","thiamin mononitrate",
    "thiamin hydrochloride","folic acid","folate",
    "calcium","iron","zinc","magnesium","potassium","phosphorus",
    "reduced iron","ferrous sulfate",
    "ascorbic acid","dough conditioner",
    # Dairy & cheese
    "milk","whole milk","skim milk","cream","butter","cheese",
    "cheddar","cheddar cheese","mozzarella","yogurt","whey",
    "whey protein","whey protein concentrate","casein",
    "buttermilk","milk powder","dried milk","nonfat dry milk",
    "cheese cultures","cheese seasoning","rennet","enzymes",
    # Eggs
    "eggs","egg","egg whites","egg yolks","whole eggs",
    # Natural sweeteners
    "honey","honey powder","maple syrup","agave",
    "date syrup","coconut sugar","stevia","steviol glycosides",
    # Fruits & vegetables
    "apple","banana","strawberry","blueberry","raspberry","cherry",
    "cranberry","candied cranberry",
    "tomato","carrot","spinach","onion","chopped onion","garlic",
    "ginger","chilli","chillies","chili","red chilli","dried red chilli",
    "red chilli powder","chilli powder",
    "beet","lemon","orange","lime","grape","pineapple","mango",
    "potato","sweet potato","vegetables","corn",
    # Spices & herbs
    "cinnamon","vanilla","vanilla extract","turmeric","paprika",
    "cumin","coriander","pepper","black pepper","oregano",
    "basil","thyme","rosemary","mint","parsley",
    "spices","spices and condiments","spices & condiments","condiments",
    # Nuts & seeds
    "almonds","walnuts","cashews","pecans","hazelnuts",
    "sunflower seeds","pumpkin seeds","chia seeds","flaxseeds",
    "sesame seeds","tahini",
    # Proteins & legumes
    "peanuts","peanut butter","lentils","chickpeas","beans",
    "soy","tofu","tempeh","soy protein",
    # Oils
    "olive oil","extra virgin olive oil","coconut oil","avocado oil",
    "soybean oil","soyabean oil","canola oil","sunflower oil",
    "edible vegetable oil","corn oil",
    # Flavours
    "natural flavor","natural flavors","natural flavour","natural flavours",
    # Other benign
    "water","yeast","vinegar","apple cider vinegar","lemon juice",
    "cocoa","cocoa powder","dark chocolate","vanilla bean",
    "gelatin","pectin","agar","corn starch","tapioca starch",
    "annatto","beta-carotene","curcumin","carmine",
    "locust bean gum","acacia gum",
    "sorbitol","mannitol","glycerol",
    "tocopherols","alpha-tocopherol",
    "potassium sorbate","sorbic acid",
    "sodium propionate","calcium propionate",
    "citric acid","lactic acid","acetic acid",
    "cereal extract","malt extract",
}


def score_ingredient(data: dict) -> str:
    name = data.get("name", "").lower().strip()
    if _matches_any(name, NON_FOOD):  return "toxic"
    if _matches_any(name, AVOID):     return "avoid"
    e = data.get("e_number", "").lower()
    if e and _matches_any(e, AVOID):  return "avoid"
    if data.get("fda_adverse_events", 0) > 500: return "avoid"
    if _matches_any(name, CAUTION):   return "caution"
    if data.get("palm_oil"):          return "caution"
    if _matches_any(name, SAFE):      return "safe"
    if data.get("vegan") and data.get("fda_adverse_events", 0) == 0: return "safe"
    return "unknown"


def overall_score(statuses: list[str]) -> str:
    if not statuses: return "ok"
    if statuses.count("toxic") > 0:  return "not_food"
    avoid = statuses.count("avoid")
    caution = statuses.count("caution")
    total = len(statuses)
    if avoid >= 2 or (avoid == 1 and avoid / total > 0.1): return "bad"
    if avoid == 1 or caution / total > 0.3:                return "ok"
    return "great"


def _matches_any(name: str, word_set: set) -> bool:
    if name in word_set:
        return True
    for entry in word_set:
        if re.search(r'(?<![a-z])' + re.escape(entry) + r'(?![a-z])', name):
            return True
    return False

"""
modules/enricher.py — Async ingredient enrichment from free public APIs.

APIs used (all free, no API key required):
  1. OpenFoodFacts  — additive / E-number data, risk level, vegan/organic flags
  2. OpenFDA        — food adverse event reports, GRAS status lookups
  3. Wikipedia REST — plain English summary (perfect for kid explanation)
  4. Wikidata SPARQL— structured properties (LD50, allergenic, ban status)

All four are fired concurrently with asyncio.gather().
Results are merged into a single flat dict that scorer.py consumes.
"""
import asyncio
import re
import httpx

TIMEOUT = 8  # seconds per request
HEADERS = {"User-Agent": "FoodDetectiveKidsApp/1.0 (educational; contact@fooddetective.local)"}


async def enrich_ingredient(name: str) -> dict:
    """Fetch from all sources in parallel, merge, return unified dict."""
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        results = await asyncio.gather(
            _openfoodfacts(client, name),
            _openfda(client, name),
            _wikipedia(client, name),
            _wikidata(client, name),
            return_exceptions=True,
        )

    off, fda, wiki, wd = results

    merged = {}

    # OpenFoodFacts is the most authoritative for additives
    if isinstance(off, dict):
        merged.update(off)

    # OpenFDA adverse events count
    if isinstance(fda, dict):
        merged["fda_adverse_events"] = fda.get("adverse_events", 0)
        merged["fda_gras"] = fda.get("gras", None)

    # Wikipedia summary (use as kid-friendly description base)
    if isinstance(wiki, dict):
        merged["summary"] = wiki.get("summary", "")
        merged["wiki_url"] = wiki.get("url", "")

    # Wikidata structured properties
    if isinstance(wd, dict):
        merged.update(wd)

    merged["name"] = name
    return merged


# ---------------------------------------------------------------------------
# Source 1: OpenFoodFacts
# ---------------------------------------------------------------------------

async def _openfoodfacts(client: httpx.AsyncClient, name: str) -> dict:
    """
    Query the OpenFoodFacts ingredient/additive API.
    Tries the additives endpoint first (great for E-numbers), then ingredient search.
    """
    result = {}

    # Try as an additive (E-number or common name)
    slug = _to_slug(name)
    url = f"https://world.openfoodfacts.org/additive/{slug}.json"
    try:
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            products = data.get("products", [])
            if products:
                # Extract additive metadata from the first product that lists it
                for product in products[:3]:
                    additives_tags = product.get("additives_tags", [])
                    for tag in additives_tags:
                        if slug in tag:
                            result["e_number"] = tag.replace("en:", "").upper()
                            break
                # Risk level from OFF taxonomy
                result["off_found"] = True
    except Exception:
        pass

    # Query the ingredient analysis endpoint
    try:
        search_url = (
            f"https://world.openfoodfacts.org/cgi/search.pl"
            f"?search_terms={name}&search_simple=1&action=process&json=1&page_size=3"
        )
        r = await client.get(search_url)
        if r.status_code == 200:
            data = r.json()
            products = data.get("products", [])
            if products:
                p = products[0]
                # Collect ingredient-level risk signals from the first product
                ingredients_analysis = p.get("ingredients_analysis_tags", [])
                result["vegan"] = "en:vegan" in ingredients_analysis
                result["non_vegan"] = "en:non-vegan" in ingredients_analysis
                result["palm_oil"] = "en:palm-oil" in ingredients_analysis

                # Additives with risk levels
                additives = p.get("additives_original_tags", [])
                for a in additives:
                    if slug in a.lower() or name.lower().replace(" ", "-") in a.lower():
                        result["in_additive_list"] = True
                        break

                # Nutriment — check if ingredient is pure sugar / salt
                nutriments = p.get("nutriments", {})
                result["nutriments_sample"] = {
                    k: v for k, v in nutriments.items()
                    if k in ("sugars_100g", "salt_100g", "saturated-fat_100g")
                }
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Source 2: OpenFDA
# ---------------------------------------------------------------------------

async def _openfda(client: httpx.AsyncClient, name: str) -> dict:
    result = {}

    # Food adverse events search
    try:
        url = (
            "https://api.fda.gov/food/event.json"
            f'?search=reactions:"{name}"&limit=1'
        )
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            result["adverse_events"] = data.get("meta", {}).get("results", {}).get("total", 0)
    except Exception:
        result["adverse_events"] = 0

    # Check GRAS (Generally Recognised As Safe) list via substance endpoint
    try:
        url = (
            "https://api.fda.gov/other/substance.json"
            f'?search=substance_name:"{name}"&limit=1'
        )
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            if results:
                # GRAS substances have regulatory_body entries
                reg = results[0].get("codes", [])
                result["gras"] = any("GRAS" in str(c) for c in reg)
    except Exception:
        result["gras"] = None

    return result


# ---------------------------------------------------------------------------
# Source 3: Wikipedia REST API
# ---------------------------------------------------------------------------

async def _wikipedia(client: httpx.AsyncClient, name: str) -> dict:
    result = {}
    title = name.replace(" ", "_").title()
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    try:
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            extract = data.get("extract", "")
            # Keep only the first 2 sentences for brevity
            sentences = re.split(r"(?<=[.!?])\s+", extract)
            result["summary"] = " ".join(sentences[:2])
            result["url"] = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        else:
            # Try with common suffixes
            for suffix in [" (food additive)", " (additive)", " (chemical)"]:
                alt = (name + suffix).replace(" ", "_").title()
                r2 = await client.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{alt}"
                )
                if r2.status_code == 200:
                    data = r2.json()
                    extract = data.get("extract", "")
                    sentences = re.split(r"(?<=[.!?])\s+", extract)
                    result["summary"] = " ".join(sentences[:2])
                    break
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Source 4: Wikidata SPARQL
# ---------------------------------------------------------------------------

_WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

_SPARQL_TEMPLATE = """
SELECT ?item ?itemLabel ?cas ?e_number ?hazard WHERE {{
  ?item rdfs:label "{name}"@en.
  OPTIONAL {{ ?item wdt:P231 ?cas. }}
  OPTIONAL {{ ?item wdt:P628 ?e_number. }}
  OPTIONAL {{ ?item wdt:P5806 ?hazard. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 1
"""

async def _wikidata(client: httpx.AsyncClient, name: str) -> dict:
    result = {}
    query = _SPARQL_TEMPLATE.format(name=name.lower())
    try:
        r = await client.get(
            _WIKIDATA_SPARQL,
            params={"query": query, "format": "json"},
            headers={**HEADERS, "Accept": "application/sparql-results+json"},
        )
        if r.status_code == 200:
            bindings = r.json().get("results", {}).get("bindings", [])
            if bindings:
                b = bindings[0]
                if "cas" in b:
                    result["cas_number"] = b["cas"]["value"]
                if "e_number" in b:
                    result["e_number"] = b["e_number"]["value"]
                if "hazard" in b:
                    result["wikidata_hazard"] = b["hazard"]["value"]
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_slug(name: str) -> str:
    """Convert ingredient name to URL slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug

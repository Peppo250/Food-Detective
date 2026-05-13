"""
modules/enricher.py — Async ingredient enrichment from 4 free public APIs.
All fired concurrently with asyncio.gather(). No API keys required.
"""
import asyncio
import re
import httpx

TIMEOUT = 8
HEADERS = {"User-Agent": "FoodDetectiveKidsApp/1.0 (educational)"}


async def enrich_ingredient(name: str) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        results = await asyncio.gather(
            _openfoodfacts(client, name),
            _openfda(client, name),
            _wikipedia(client, name),
            _wikidata(client, name),
            return_exceptions=True,
        )
    off, fda, wiki, wd = results
    merged = {"name": name}
    if isinstance(off,  dict): merged.update(off)
    if isinstance(fda,  dict): merged["fda_adverse_events"] = fda.get("adverse_events", 0)
    if isinstance(wiki, dict): merged["summary"] = wiki.get("summary", "")
    if isinstance(wd,   dict): merged.update(wd)
    return merged


async def _openfoodfacts(client, name):
    result = {}
    try:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        r = await client.get(
            f"https://world.openfoodfacts.org/cgi/search.pl"
            f"?search_terms={name}&search_simple=1&action=process&json=1&page_size=3")
        if r.status_code == 200:
            data = r.json()
            products = data.get("products", [])
            if products:
                p = products[0]
                tags = p.get("ingredients_analysis_tags", [])
                result["vegan"]    = "en:vegan" in tags
                result["palm_oil"] = "en:palm-oil" in tags
                additives = p.get("additives_original_tags", [])
                for a in additives:
                    if slug in a.lower():
                        result["in_additive_list"] = True
                        break
    except Exception:
        pass
    return result


async def _openfda(client, name):
    result = {"adverse_events": 0}
    try:
        r = await client.get(
            f'https://api.fda.gov/food/event.json?search=reactions:"{name}"&limit=1')
        if r.status_code == 200:
            data = r.json()
            result["adverse_events"] = data.get("meta", {}).get("results", {}).get("total", 0)
    except Exception:
        pass
    return result


async def _wikipedia(client, name):
    result = {}
    title = name.replace(" ", "_").title()
    try:
        r = await client.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}")
        if r.status_code == 200:
            data = r.json()
            extract = data.get("extract", "")
            sentences = re.split(r"(?<=[.!?])\s+", extract)
            result["summary"] = " ".join(sentences[:2])
        else:
            for suffix in [" (food additive)", " (additive)"]:
                alt = (name + suffix).replace(" ", "_").title()
                r2 = await client.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{alt}")
                if r2.status_code == 200:
                    data = r2.json()
                    extract = data.get("extract", "")
                    sentences = re.split(r"(?<=[.!?])\s+", extract)
                    result["summary"] = " ".join(sentences[:2])
                    break
    except Exception:
        pass
    return result


_SPARQL = "https://query.wikidata.org/sparql"
_SPARQL_Q = """
SELECT ?item ?cas ?e_number WHERE {{
  ?item rdfs:label "{name}"@en.
  OPTIONAL {{ ?item wdt:P231 ?cas. }}
  OPTIONAL {{ ?item wdt:P628 ?e_number. }}
}} LIMIT 1
"""


async def _wikidata(client, name):
    result = {}
    try:
        r = await client.get(
            _SPARQL,
            params={"query": _SPARQL_Q.format(name=name.lower()), "format": "json"},
            headers={**HEADERS, "Accept": "application/sparql-results+json"})
        if r.status_code == 200:
            bindings = r.json().get("results", {}).get("bindings", [])
            if bindings:
                b = bindings[0]
                if "e_number" in b:
                    result["e_number"] = b["e_number"]["value"]
    except Exception:
        pass
    return result

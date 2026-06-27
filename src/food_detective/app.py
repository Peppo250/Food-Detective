"""
app.py — FastAPI application.
Exposes POST /scan — accepts an image, streams ingredient results as SSE,
then emits a daily_advice event at the end.
"""
import json
import asyncio
import httpx
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from food_detective.modules.ocr import extract_ingredients_from_image
from food_detective.modules.cache import IngredientCache
from food_detective.modules.enricher import enrich_ingredient
from food_detective.modules.scorer import score_ingredient, overall_score
from food_detective.modules.explainer import make_kid_explanation
from food_detective.modules.daily_limits import compute_product_advice


def create_app() -> FastAPI:
    app = FastAPI(title="Food Detective API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    cache = IngredientCache()

    @app.on_event("startup")
    async def startup():
        cache.purge_expired()
        from food_detective.modules.enricher import TIMEOUT, HEADERS
        app.state.client = httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS)

    @app.on_event("shutdown")
    async def shutdown():
        if hasattr(app.state, "client"):
            await app.state.client.aclose()

    @app.post("/scan")
    async def scan(file: UploadFile = File(...)):
        image_bytes = await file.read()

        async def event_stream():
            yield _sse("status", {"message": "Reading the label..."})

            try:
                ingredients = await asyncio.to_thread(extract_ingredients_from_image, image_bytes)
            except Exception as e:
                yield _sse("error", {"message": f"Could not read label: {e}"})
                return

            if not ingredients:
                yield _sse("error", {"message": "No ingredients found — try a clearer photo!"})
                return

            yield _sse("parsed", {"ingredients": ingredients})
            yield _sse("status", {"message": f"Found {len(ingredients)} ingredients! Checking each one..."})

            # Check cache / fetch
            hits, misses = [], []
            for name in ingredients:
                cached = cache.get(name)
                if cached:
                    hits.append((name, cached))
                else:
                    misses.append(name)

            # Stream cache hits immediately
            for name, data in hits:
                data["from_cache"] = True
                yield _sse("ingredient", data)
                await asyncio.sleep(0)

            # Fetch misses in parallel batches
            all_results = list(hits)
            BATCH = 5
            for i in range(0, len(misses), BATCH):
                batch = misses[i:i + BATCH]
                batch_results = await asyncio.gather(
                    *[_fetch_and_build(name, cache, app.state.client) for name in batch],
                    return_exceptions=True,
                )
                for name, result in zip(batch, batch_results):
                    if isinstance(result, Exception):
                        result = _fallback_entry(name)
                    result["from_cache"] = False
                    all_results.append((name, result))
                    yield _sse("ingredient", result)
                    await asyncio.sleep(0)

            # Overall score
            all_statuses = [d["status"] for _, d in all_results]
            score = overall_score(all_statuses)
            yield _sse("done", {"overall_score": score})

            # Daily advice — needs the raw OCR text, which we reconstruct
            # from ingredient names (the actual OCR text isn't stored here;
            # the daily advice module works on whatever text we pass it)
            # For now pass the ingredient list — the module picks up additive limits
            try:
                advice = compute_product_advice(
                    [name for name, _ in all_results],
                    ocr_text="",        # no raw text here; serving/nutriment parsing
                    product_name="this product",  # will be set by UI if known
                )
                yield _sse("daily_advice", {
                    "summary": advice.summary,
                    "detail_lines": advice.detail_lines,
                    "max_servings": advice.max_servings_display,
                    "limiting": advice.limiting_ingredient,
                    "serving_size_g": advice.serving_size_g,
                })
            except Exception:
                pass  # daily advice is best-effort

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


async def _fetch_and_build(name: str, cache: "IngredientCache", client: httpx.AsyncClient) -> dict:
    raw = await enrich_ingredient(name, client)
    status = score_ingredient(raw)
    explanation = make_kid_explanation(name, status, raw)
    entry = {
        "name": name,
        "status": status,
        "explanation": explanation,
        "what_is_it": raw.get("summary", ""),
        "e_number": raw.get("e_number", ""),
        "risk_level": raw.get("risk_level", ""),
    }
    cache.set(name, entry)
    return entry


def _fallback_entry(name: str) -> dict:
    return {
        "name": name,
        "status": "unknown",
        "explanation": "We couldn't find information about this ingredient right now.",
        "what_is_it": "",
        "e_number": "",
        "risk_level": "",
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

"""
app.py — FastAPI application factory.
Exposes POST /scan which accepts an image and streams ingredient results as SSE.
"""
import json
import asyncio
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from modules.ocr import extract_ingredients_from_image
from modules.cache import IngredientCache
from modules.enricher import enrich_ingredient
from modules.scorer import score_ingredient, overall_score
from modules.explainer import make_kid_explanation


def create_app() -> FastAPI:
    app = FastAPI(title="Food Detective API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    cache = IngredientCache()

    @app.on_event("startup")
    async def startup():
        cache.purge_expired()

    @app.post("/scan")
    async def scan(file: UploadFile = File(...)):
        image_bytes = await file.read()

        async def event_stream():
            # Step 1: OCR — yield a status ping first so UI shows activity
            yield _sse("status", {"message": "Reading the label..."})

            try:
                ingredients = extract_ingredients_from_image(image_bytes)
            except Exception as e:
                yield _sse("error", {"message": f"Could not read label: {e}"})
                return

            if not ingredients:
                yield _sse("error", {"message": "No ingredients found — try a clearer photo!"})
                return

            # Emit parsed list to debug tab
            yield _sse("parsed", {"ingredients": ingredients})
            yield _sse("status", {"message": f"Found {len(ingredients)} ingredients! Checking each one..."})

            # Step 2: check cache then fetch misses in parallel
            hits = []
            misses = []
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
            all_results = []
            BATCH = 5
            for i in range(0, len(misses), BATCH):
                batch = misses[i:i + BATCH]
                batch_results = await asyncio.gather(
                    *[_fetch_and_build(name, cache) for name in batch],
                    return_exceptions=True,
                )
                for name, result in zip(batch, batch_results):
                    if isinstance(result, Exception):
                        result = _fallback_entry(name)
                    result["from_cache"] = False
                    all_results.append((name, result))
                    yield _sse("ingredient", result)
                    await asyncio.sleep(0)

            # Overall score from all statuses
            all_statuses = [d["status"] for _, d in hits] + [d["status"] for _, d in all_results]
            score = overall_score(all_statuses)
            yield _sse("done", {"overall_score": score})

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


async def _fetch_and_build(name: str, cache: "IngredientCache") -> dict:
    raw = await enrich_ingredient(name)
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

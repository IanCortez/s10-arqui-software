"""
Search API — entry point del sistema.

POST /poke/search
    Request:  { "Pokemon_Name": "charizard" }
    Response: { "name": "charizard", "stats": {...}, "image": "<url>" }

Orquesta llamadas a PokeApi, PokeStats y PokeImages, midiendo latencia de cada
bloque de código.
"""
import os
import sys
import time
import asyncio
from pathlib import Path

# Permite import de `common` cuando se corre con uvicorn directo
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from common.logger import get_logger, log_block, log_request

MODULE = "SEARCH_API"
logger = get_logger(MODULE)

POKE_API_URL = os.getenv("POKE_API_URL", "http://localhost:8001")
POKE_STATS_URL = os.getenv("POKE_STATS_URL", "http://localhost:8002")
POKE_IMAGES_URL = os.getenv("POKE_IMAGES_URL", "http://localhost:8003")

app = FastAPI(title="Search API", version="1.0.0")


class SearchRequest(BaseModel):
    Pokemon_Name: str


@app.post("/poke/search")
async def search_pokemon(req: SearchRequest):
    api = "/poke/search"
    fn = "search_pokemon"
    name = req.Pokemon_Name.lower().strip()
    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:

            # Llamadas en paralelo para reducir latencia total
            async def call_poke_api():
                with log_block(logger, MODULE, api, "call_poke_api") as ctx:
                    r = await client.get(f"{POKE_API_URL}/pokemon/{name}")
                    ctx["status"] = r.status_code
                    r.raise_for_status()
                    return r.json()

            async def call_poke_stats():
                with log_block(logger, MODULE, api, "call_poke_stats") as ctx:
                    r = await client.get(f"{POKE_STATS_URL}/stats/{name}")
                    ctx["status"] = r.status_code
                    return r.json() if r.status_code == 200 else {}

            async def call_poke_images():
                with log_block(logger, MODULE, api, "call_poke_images") as ctx:
                    r = await client.get(f"{POKE_IMAGES_URL}/image/{name}")
                    ctx["status"] = r.status_code
                    return r.json().get("url") if r.status_code == 200 else None

            base, stats, image = await asyncio.gather(
                call_poke_api(), call_poke_stats(), call_poke_images()
            )

        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 200,
                    f"search_ok name={name}")
        return {"name": base.get("name"), "stats": stats, "image": image}

    except httpx.HTTPStatusError as e:
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 500,
                    f"upstream_error name={name} err={e}")
        raise HTTPException(status_code=500, detail="Upstream error")
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 500,
                    f"internal_error name={name} err={e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/health")
def health():
    return {"status": "ok", "service": MODULE}

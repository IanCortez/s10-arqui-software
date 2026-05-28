"""
PokeApi microservice — proxy hacia pokeapi.co/api/v2/pokemon/{name}.

Incluye:
- Cache en memoria para no saturar la API pública.
- Inyección controlada de errores (~8%) para que las métricas tengan variedad.
"""
import os
import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from fastapi import FastAPI, HTTPException
from common.logger import get_logger, log_block, log_request, log_request_start

MODULE = "POKE_API"
logger = get_logger(MODULE)
app = FastAPI(title="Poke API")

POKE_UPSTREAM = "https://pokeapi.co/api/v2/pokemon"
ERROR_RATE = float(os.getenv("ERROR_RATE", "0.08"))
_cache: dict = {}


@app.get("/pokemon/{name}")
async def get_pokemon(name: str):
    api = f"/pokemon/{{name}}"
    fn = "get_pokemon"
    start = time.perf_counter()
    name = name.lower().strip()
    request_id = log_request_start(logger, MODULE, api, fn, query=name)

    # Inyección de error sintético para alimentar métricas
    if random.random() < ERROR_RATE:
        # Latencia añadida para simular timeout/upstream lento
        time.sleep(random.uniform(0.2, 0.6))
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 500,
                    f"injected_failure name={name}", request_id=request_id, query=name)
        raise HTTPException(status_code=500, detail="Simulated upstream failure")

    try:
        with log_block(logger, MODULE, api, "cache_lookup", request_id, name) as ctx:
            cached = _cache.get(name)
            ctx["status"] = "HIT" if cached else "MISS"

        if cached:
            elapsed = (time.perf_counter() - start) * 1000
            log_request(logger, MODULE, api, fn, elapsed, 200,
                        f"cache_hit name={name}", request_id=request_id, query=name)
            return cached

        with log_block(logger, MODULE, api, "upstream_fetch", request_id, name) as ctx:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(f"{POKE_UPSTREAM}/{name}")
                ctx["status"] = r.status_code
                r.raise_for_status()
                data = r.json()

        slim = {
            "name": data.get("name"),
            "id": data.get("id"),
            "height": data.get("height"),
            "weight": data.get("weight"),
            "types": [t["type"]["name"] for t in data.get("types", [])],
        }
        _cache[name] = slim
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 200,
                    f"fetched name={name}", request_id=request_id, query=name)
        return slim

    except httpx.HTTPStatusError:
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 500,
                    f"not_found_upstream name={name}", request_id=request_id, query=name)
        raise HTTPException(status_code=500, detail="Upstream not found")
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 500,
                    f"internal_error name={name} err={e}", request_id=request_id, query=name)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/health")
def health():
    return {"status": "ok", "service": MODULE}

"""
PokeImages microservice — devuelve URL de imagen para un pokemon.

En producción real apuntaría a S3 / File Server con el dataset de Kaggle
(hlrhegemony/pokemon-image-dataset). Aquí devolvemos la URL del sprite oficial
de pokeapi para que sea reproducible.
"""
import os
import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI, HTTPException
from common.logger import get_logger, log_block, log_request, log_request_start

MODULE = "POKE_IMAGES"
logger = get_logger(MODULE)
app = FastAPI(title="Poke Images")

BASE_IMG_URL = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork"
)
ERROR_RATE = float(os.getenv("ERROR_RATE", "0.10"))


# Mapeo mínimo nombre -> id (los más populares; ampliable)
_NAME_TO_ID = {
    "bulbasaur": 1, "ivysaur": 2, "venusaur": 3,
    "charmander": 4, "charmeleon": 5, "charizard": 6,
    "squirtle": 7, "wartortle": 8, "blastoise": 9,
    "caterpie": 10, "butterfree": 12, "weedle": 13, "beedrill": 15,
    "pidgey": 16, "pidgeotto": 17, "pidgeot": 18,
    "rattata": 19, "raticate": 20,
    "pikachu": 25, "raichu": 26,
    "sandshrew": 27, "clefairy": 35,
    "vulpix": 37, "ninetales": 38, "jigglypuff": 39,
    "zubat": 41, "oddish": 43, "meowth": 52,
    "psyduck": 54, "machop": 66, "geodude": 74,
    "magikarp": 129, "gyarados": 130,
    "eevee": 133, "snorlax": 143,
    "mewtwo": 150, "mew": 151,
}


@app.get("/image/{name}")
def get_image(name: str):
    api = "/image/{name}"
    fn = "get_image"
    start = time.perf_counter()
    name = name.lower().strip()
    request_id = log_request_start(logger, MODULE, api, fn, query=name)

    if random.random() < ERROR_RATE:
        # Simulamos S3 lento + caída
        time.sleep(random.uniform(0.3, 0.8))
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 500,
                    f"injected_s3_failure name={name}", request_id=request_id, query=name)
        raise HTTPException(status_code=500, detail="Simulated S3 failure")

    try:
        with log_block(logger, MODULE, api, "file_lookup", request_id, name) as ctx:
            poke_id = _NAME_TO_ID.get(name)
            ctx["status"] = "FOUND" if poke_id else "MISS"

        if not poke_id:
            elapsed = (time.perf_counter() - start) * 1000
            log_request(logger, MODULE, api, fn, elapsed, 404,
                        f"image_not_found name={name}", request_id=request_id, query=name)
            raise HTTPException(status_code=404, detail="Image not found")

        url = f"{BASE_IMG_URL}/{poke_id}.png"
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 200,
                    f"image_ok name={name}", request_id=request_id, query=name)
        return {"name": name, "url": url}

    except HTTPException:
        raise
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 500,
                    f"internal_error name={name} err={e}", request_id=request_id, query=name)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/health")
def health():
    return {"status": "ok", "service": MODULE}

"""
PokeStats microservice — sirve las stats clásicas desde SQLite.

Las stats vienen del dataset de Kaggle (abcsds/pokemon). Para evitar dependencia
de Kaggle al evaluar el lab, se incluye `seed_db.py` que carga ~30 pokemones
populares directamente.
"""
import os
import sys
import time
import random
import sqlite3
from pathlib import Path

_here = Path(__file__).resolve()
sys.path.insert(0, str(_here.parents[2] if len(_here.parents) > 2 else _here.parent))

from fastapi import FastAPI, HTTPException
from common.logger import get_logger, log_block, log_request, log_request_start

MODULE = "POKE_STATS"
logger = get_logger(MODULE)
app = FastAPI(title="Poke Stats")

DB_PATH = os.getenv("STATS_DB", str(Path(__file__).resolve().parent / "pokemon_stats.db"))
ERROR_RATE = float(os.getenv("ERROR_RATE", "0.05"))


def _get_conn():
    return sqlite3.connect(DB_PATH)


@app.get("/stats/{name}")
def get_stats(name: str):
    api = "/stats/{name}"
    fn = "get_stats"
    start = time.perf_counter()
    name = name.lower().strip()
    request_id = log_request_start(logger, MODULE, api, fn, query=name)

    if random.random() < ERROR_RATE:
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 500,
                    f"injected_db_failure name={name}", request_id=request_id, query=name)
        raise HTTPException(status_code=500, detail="Simulated DB failure")

    try:
        with log_block(logger, MODULE, api, "db_query", request_id, name) as ctx:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT name, hp, attack, defense, sp_attack, sp_defense, speed, total "
                "FROM pokemon_stats WHERE LOWER(name)=?",
                (name,),
            )
            row = cur.fetchone()
            conn.close()
            ctx["status"] = "FOUND" if row else "MISS"

        if not row:
            elapsed = (time.perf_counter() - start) * 1000
            log_request(logger, MODULE, api, fn, elapsed, 404,
                        f"not_found name={name}", request_id=request_id, query=name)
            raise HTTPException(status_code=404, detail="Not found")

        stats = {
            "name": row[0],
            "hp": row[1],
            "attack": row[2],
            "defense": row[3],
            "sp_attack": row[4],
            "sp_defense": row[5],
            "speed": row[6],
            "total": row[7],
        }
        elapsed = (time.perf_counter() - start) * 1000
        log_request(logger, MODULE, api, fn, elapsed, 200,
                    f"stats_ok name={name}", request_id=request_id, query=name)
        return stats

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

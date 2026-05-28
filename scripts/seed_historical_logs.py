"""
Genera logs históricos sintéticos con timestamps repartidos en los últimos 7 días.

Útil para hacer demos del bot cuando Locust solo se corrió en una ventana corta.
En producción real, los logs se acumulan naturalmente con el paso del tiempo
(este script NO es necesario en ese caso, solo es para demo).

Uso:
    PYTHONPATH=. python scripts/seed_historical_logs.py
"""
import os
import sys
import random
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

random.seed(7)

POKEMON = ["bulbasaur", "charizard", "squirtle", "pikachu", "raichu", "eevee",
           "snorlax", "mewtwo", "gyarados", "magikarp", "psyduck", "jigglypuff"]


def fmt_log(ts: datetime, module: str, api: str, func: str, level: str,
            latency_ms, status, msg: str) -> str:
    ts_str = ts.isoformat(timespec="milliseconds")
    return (f"{ts_str} | MODULE={module} | API={api} | FUNC={func} | "
            f"LEVEL={level} | LATENCY_MS={latency_ms} | STATUS={status} | MSG={msg}\n")


def simulate_request(ts: datetime) -> list[tuple[str, str]]:
    """Simula una request completa y devuelve líneas de log por archivo."""
    out: list[tuple[str, str]] = []
    name = random.choice(POKEMON)

    # POKE_API
    api_fail = random.random() < 0.08
    api_lat = random.uniform(300, 600) if api_fail else random.uniform(50, 150)
    if not api_fail:
        out.append(("poke_api", fmt_log(ts, "POKE_API", "/pokemon/{name}", "cache_lookup",
                                         "INFO", 0, "STARTED", "block_start")))
        out.append(("poke_api", fmt_log(ts + timedelta(milliseconds=0.1),
                                         "POKE_API", "/pokemon/{name}", "cache_lookup",
                                         "INFO", "0.10", "HIT", "block_end")))
        out.append(("poke_api", fmt_log(ts + timedelta(milliseconds=api_lat),
                                         "POKE_API", "/pokemon/{name}", "get_pokemon",
                                         "INFO", f"{api_lat:.2f}", 200, f"cache_hit name={name}")))
    else:
        out.append(("poke_api", fmt_log(ts + timedelta(milliseconds=api_lat),
                                         "POKE_API", "/pokemon/{name}", "get_pokemon",
                                         "ERROR", f"{api_lat:.2f}", 500, f"injected_failure name={name}")))

    # POKE_STATS
    stats_fail = random.random() < 0.05
    stats_lat = random.uniform(20, 80) if not stats_fail else random.uniform(200, 400)
    if not stats_fail:
        out.append(("poke_stats", fmt_log(ts + timedelta(milliseconds=2),
                                           "POKE_STATS", "/stats/{name}", "db_query",
                                           "INFO", 0, "STARTED", "block_start")))
        out.append(("poke_stats", fmt_log(ts + timedelta(milliseconds=2 + stats_lat),
                                           "POKE_STATS", "/stats/{name}", "get_stats",
                                           "INFO", f"{stats_lat:.2f}", 200, f"stats_ok name={name}")))
    else:
        out.append(("poke_stats", fmt_log(ts + timedelta(milliseconds=2 + stats_lat),
                                           "POKE_STATS", "/stats/{name}", "get_stats",
                                           "ERROR", f"{stats_lat:.2f}", 500, f"injected_db_failure name={name}")))

    # POKE_IMAGES (latencia más alta = bottleneck del sistema)
    img_fail = random.random() < 0.12
    # IMÁGENES tiene latencia base más alta — debe verse como el bottleneck
    img_lat = random.uniform(1500, 4000) if not img_fail else random.uniform(3000, 6000)
    if not img_fail:
        out.append(("poke_images", fmt_log(ts + timedelta(milliseconds=img_lat),
                                            "POKE_IMAGES", "/image/{name}", "get_image",
                                            "INFO", f"{img_lat:.2f}", 200, f"image_ok name={name}")))
    else:
        out.append(("poke_images", fmt_log(ts + timedelta(milliseconds=img_lat),
                                            "POKE_IMAGES", "/image/{name}", "get_image",
                                            "ERROR", f"{img_lat:.2f}", 500, f"injected_s3_failure name={name}")))

    # SEARCH_API (latencia total = max de las 3, dominada por POKE_IMAGES)
    search_lat = max(api_lat, stats_lat, img_lat) + random.uniform(2, 8)
    search_status = 500 if api_fail else 200
    search_level = "ERROR" if api_fail else "INFO"
    out.append(("search_api", fmt_log(ts + timedelta(milliseconds=search_lat),
                                       "SEARCH_API", "/poke/search", "search_pokemon",
                                       search_level, f"{search_lat:.2f}", search_status,
                                       f"name={name}")))
    return out


def generate(days: int = 7, requests_per_day: int = 1500):
    now = datetime.now(timezone.utc)
    buffers: dict[str, list[str]] = {
        "poke_api": [], "poke_stats": [], "poke_images": [], "search_api": []
    }
    total = 0
    for d in range(days, 0, -1):
        day_start = (now - timedelta(days=d)).replace(hour=8, minute=0, second=0, microsecond=0)
        for i in range(requests_per_day):
            # Distribuir los requests a lo largo de 12 horas del día
            secs = random.uniform(0, 12 * 3600)
            ts = day_start + timedelta(seconds=secs)
            for service, line in simulate_request(ts):
                buffers[service].append(line)
            total += 1

    # Escribir a disco — los buffers se ordenan por timestamp implícito en la generación
    # pero los re-ordenamos para asegurar orden cronológico estricto
    for service, lines in buffers.items():
        lines.sort()  # ISO timestamp al inicio garantiza orden cronológico
        path = LOG_DIR / f"{service}.log"
        with path.open("w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"  {path}: {len(lines)} líneas")

    print(f"\nTotal de requests generados: {total} a lo largo de {days} días")


if __name__ == "__main__":
    generate(days=7, requests_per_day=1500)

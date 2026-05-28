"""
Genera logs históricos sintéticos en la base SQLite centralizada.

Uso:
    PYTHONPATH=. python scripts/seed_historical_logs.py
"""
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.log_store import get_connection, init_db, insert_logs

random.seed(7)

POKEMON = [
    "bulbasaur", "charizard", "squirtle", "pikachu", "raichu", "eevee",
    "snorlax", "mewtwo", "gyarados", "magikarp", "psyduck", "jigglypuff",
]


def iso(ts: datetime) -> str:
    return ts.isoformat(timespec="milliseconds")


def event(
    ts: datetime,
    request_id: str,
    action: str,
    microservice: str,
    api: str,
    function: str,
    status,
    latency_ms,
    query: str,
    message: str,
) -> dict:
    status_code = status if isinstance(status, int) else None
    return {
        "timestamp": iso(ts),
        "request_id": request_id,
        "action": action,
        "microservice": microservice,
        "api": api,
        "function": function,
        "level": "ERROR" if status_code and status_code >= 400 else "INFO",
        "status": str(status),
        "status_code": status_code,
        "latency_ms": latency_ms,
        "query": query,
        "message": message,
    }


def add_request(events: list[dict], ts: datetime, service: str, api: str,
                function: str, query: str, latency_ms: float, status: int,
                message: str) -> None:
    request_id = str(uuid4())
    events.append(event(ts, request_id, "request_start", service, api, function,
                        "STARTED", None, query, "request_start"))
    action = "request_error" if status >= 400 else "request_end"
    events.append(event(ts + timedelta(milliseconds=latency_ms), request_id, action,
                        service, api, function, status, round(latency_ms, 2), query, message))


def simulate_request(ts: datetime, events: list[dict]) -> None:
    name = random.choice(POKEMON)

    api_fail = random.random() < 0.08
    api_lat = random.uniform(300, 600) if api_fail else random.uniform(50, 150)
    add_request(
        events, ts, "POKE_API", "/pokemon/{name}", "get_pokemon", name,
        api_lat, 500 if api_fail else 200,
        f"{'injected_failure' if api_fail else 'cache_hit'} name={name}",
    )

    stats_fail = random.random() < 0.05
    stats_lat = random.uniform(20, 80) if not stats_fail else random.uniform(200, 400)
    add_request(
        events, ts + timedelta(milliseconds=2), "POKE_STATS", "/stats/{name}",
        "get_stats", name, stats_lat, 500 if stats_fail else 200,
        f"{'injected_db_failure' if stats_fail else 'stats_ok'} name={name}",
    )

    img_fail = random.random() < 0.12
    img_lat = random.uniform(1500, 4000) if not img_fail else random.uniform(3000, 6000)
    add_request(
        events, ts, "POKE_IMAGES", "/image/{name}", "get_image", name,
        img_lat, 500 if img_fail else 200,
        f"{'injected_s3_failure' if img_fail else 'image_ok'} name={name}",
    )

    search_lat = max(api_lat, stats_lat, img_lat) + random.uniform(2, 8)
    search_status = 500 if api_fail else 200
    add_request(
        events, ts, "SEARCH_API", "/poke/search", "search_pokemon", name,
        search_lat, search_status,
        f"{'upstream_error' if api_fail else 'search_ok'} name={name}",
    )


def generate(days: int = 7, requests_per_day: int = 1500):
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM logs")

    now = datetime.now(timezone.utc)
    events: list[dict] = []
    total = 0
    for d in range(days, 0, -1):
        day_start = (now - timedelta(days=d)).replace(hour=8, minute=0, second=0, microsecond=0)
        for _ in range(requests_per_day):
            ts = day_start + timedelta(seconds=random.uniform(0, 12 * 3600))
            simulate_request(ts, events)
            total += 1

    events.sort(key=lambda item: item["timestamp"])
    insert_logs(events)

    print(f"Inserted {len(events)} log events for {total} synthetic requests")


if __name__ == "__main__":
    generate(days=7, requests_per_day=1500)

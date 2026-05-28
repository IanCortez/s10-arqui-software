"""
Parser de logs de los microservicios.

Lee la base SQLite centralizada configurada por `LOG_DB_PATH` y devuelve
registros como diccionarios listos para agregaciones.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from common.log_store import query_logs

LOG_DIR = Path("logs")

# Aliases amigables que acepta el bot -> nombre interno del módulo
MODULE_ALIASES = {
    "searchapi": "SEARCH_API",
    "search": "SEARCH_API",
    "pokeapi": "POKE_API",
    "pokestats": "POKE_STATS",
    "stats": "POKE_STATS",
    "pokeimages": "POKE_IMAGES",
    "pokeimage": "POKE_IMAGES",
    "images": "POKE_IMAGES",
}

def normalize_module(name: str) -> str:
    key = name.lower().replace("_", "").replace("-", "").strip()
    return MODULE_ALIASES.get(key, name.upper())


def _parse_db_record(record: dict) -> Optional[dict]:
    try:
        ts = datetime.fromisoformat(record["timestamp"])
    except ValueError:
        return None
    return {
        "ts": ts,
        "request_id": record.get("request_id"),
        "action": record.get("action"),
        "module": record.get("microservice"),
        "api": record.get("api"),
        "func": record.get("function"),
        "level": record.get("level"),
        "latency_ms": record.get("latency_ms"),
        "status": record.get("status"),
        "status_int": record.get("status_code"),
        "query": record.get("query"),
        "msg": record.get("message"),
    }


def read_logs(module: Optional[str] = None,
              start: Optional[datetime] = None,
              end: Optional[datetime] = None,
              log_dir: Path = LOG_DIR) -> list[dict]:
    """Lee y filtra logs. Si module es None, lee todos."""
    del log_dir
    records = query_logs(
        microservice=normalize_module(module) if module else None,
        start=start.isoformat(timespec="milliseconds") if start else None,
        end=end.isoformat(timespec="milliseconds") if end else None,
        limit=100000,
    )
    parsed = [_parse_db_record(record) for record in records]
    return [record for record in parsed if record is not None]


def parse_date(s: str) -> datetime:
    """Acepta DD/MM, DD/MM/YYYY, o YYYY-MM-DD."""
    s = s.strip()
    formats = ["%d/%m/%Y", "%d/%m", "%Y-%m-%d"]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%d/%m":
                dt = dt.replace(year=datetime.now(timezone.utc).year)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Formato de fecha inválido: {s}")


def last_n_days(n: int) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=n)
    return start, end


def parse_window(token: str) -> tuple[datetime, datetime]:
    """Acepta -Last5Days, -Last7Days, Last3Days, etc."""
    t = token.lstrip("-").lower().replace("last", "").replace("days", "")
    return last_n_days(int(t))


# Endpoints que cuentan como request HTTP de entrada (no bloques internos)
REQUEST_FUNCS = {
    "search_pokemon", "get_pokemon", "get_stats", "get_image",
}


def request_records(records: list[dict]) -> list[dict]:
    """Filtra solo los registros que representan un request HTTP completo
    (descarta block_start/block_end internos para no contar doble)."""
    return [
        r for r in records
        if r["action"] in {"request_end", "request_error"}
        and r["func"] in REQUEST_FUNCS
        and r["status_int"] is not None
    ]

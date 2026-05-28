"""
Parser de logs de los microservicios.

Lee los archivos en `logs/` con formato:
    {ISO_TS} | MODULE=<m> | API=<a> | FUNC=<f> | LEVEL=<l> | LATENCY_MS=<ms> | STATUS=<s> | MSG=<m>

Devuelve registros como diccionarios listos para agregaciones.
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

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

LINE_RE = re.compile(
    r"^(?P<ts>[^|]+?) \| MODULE=(?P<mod>[^|]+?) \| API=(?P<api>[^|]+?) \| "
    r"FUNC=(?P<fn>[^|]+?) \| LEVEL=(?P<lvl>[^|]+?) \| LATENCY_MS=(?P<lat>[^|]+?) \| "
    r"STATUS=(?P<st>[^|]+?) \| MSG=(?P<msg>.*)$"
)


def normalize_module(name: str) -> str:
    key = name.lower().replace("_", "").replace("-", "").strip()
    return MODULE_ALIASES.get(key, name.upper())


def _parse_line(line: str) -> Optional[dict]:
    m = LINE_RE.match(line.rstrip("\n"))
    if not m:
        return None
    d = m.groupdict()
    try:
        ts = datetime.fromisoformat(d["ts"].strip())
    except ValueError:
        return None
    try:
        latency = float(d["lat"].strip())
    except ValueError:
        latency = None
    status = d["st"].strip()
    try:
        status_int = int(status)
    except ValueError:
        status_int = None
    return {
        "ts": ts,
        "module": d["mod"].strip(),
        "api": d["api"].strip(),
        "func": d["fn"].strip(),
        "level": d["lvl"].strip(),
        "latency_ms": latency,
        "status": status,
        "status_int": status_int,
        "msg": d["msg"].strip(),
    }


def read_logs(module: Optional[str] = None,
              start: Optional[datetime] = None,
              end: Optional[datetime] = None,
              log_dir: Path = LOG_DIR) -> list[dict]:
    """Lee y filtra logs. Si module es None, lee todos."""
    if not log_dir.exists():
        return []

    files: Iterable[Path]
    if module:
        target = normalize_module(module).lower()
        files = log_dir.glob(f"{target}.log")
    else:
        files = log_dir.glob("*.log")

    records = []
    for f in files:
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                rec = _parse_line(line)
                if not rec:
                    continue
                if start and rec["ts"] < start:
                    continue
                if end and rec["ts"] > end:
                    continue
                records.append(rec)
    return records


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
    return [r for r in records if r["func"] in REQUEST_FUNCS and r["status_int"] is not None]

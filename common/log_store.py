import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


LOG_DB_PATH = Path(os.getenv("LOG_DB_PATH", "logs/central_logs.db"))


def get_log_db_path() -> Path:
    return Path(os.getenv("LOG_DB_PATH", str(LOG_DB_PATH)))


def get_connection() -> sqlite3.Connection:
    db_path = get_log_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def normalize_microservice(name: str) -> str:
    aliases = {
        "searchapi": "SEARCH_API",
        "search": "SEARCH_API",
        "pokeapi": "POKE_API",
        "pokestats": "POKE_STATS",
        "stats": "POKE_STATS",
        "pokeimages": "POKE_IMAGES",
        "pokeimage": "POKE_IMAGES",
        "images": "POKE_IMAGES",
    }
    key = name.lower().replace("_", "").replace("-", "").strip()
    return aliases.get(key, name.upper())


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                request_id TEXT,
                action TEXT NOT NULL,
                microservice TEXT NOT NULL,
                api TEXT,
                function TEXT,
                level TEXT NOT NULL,
                status TEXT,
                status_code INTEGER,
                latency_ms REAL,
                query TEXT,
                message TEXT,
                metadata_json TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_microservice ON logs(microservice)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_action ON logs(action)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_request_id ON logs(request_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_status_code ON logs(status_code)")


def insert_log(event: dict[str, Any]) -> None:
    init_db()
    values = _event_values(event)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO logs (
                timestamp, request_id, action, microservice, api, function, level,
                status, status_code, latency_ms, query, message, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )


def insert_logs(events: list[dict[str, Any]]) -> None:
    init_db()
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO logs (
                timestamp, request_id, action, microservice, api, function, level,
                status, status_code, latency_ms, query, message, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [_event_values(event) for event in events],
        )


def _event_values(event: dict[str, Any]) -> tuple:
    metadata = event.get("metadata")
    metadata_json = json.dumps(metadata, sort_keys=True) if metadata else None
    return (
        event["timestamp"],
        event.get("request_id"),
        event["action"],
        event["microservice"],
        event.get("api"),
        event.get("function"),
        event["level"],
        event.get("status"),
        event.get("status_code"),
        event.get("latency_ms"),
        event.get("query"),
        event.get("message"),
        metadata_json,
    )


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    records = []
    for row in rows:
        item = dict(row)
        if item.get("metadata_json"):
            item["metadata"] = json.loads(item["metadata_json"])
        else:
            item["metadata"] = {}
        item.pop("metadata_json", None)
        records.append(item)
    return records


def query_logs(
    *,
    microservice: str | None = None,
    action: str | None = None,
    status_code: int | None = None,
    level: str | None = None,
    query: str | None = None,
    request_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    init_db()
    filters: list[str] = []
    params: list[Any] = []

    if microservice:
        filters.append("microservice = ?")
        params.append(normalize_microservice(microservice))
    if action:
        filters.append("action = ?")
        params.append(action)
    if status_code is not None:
        filters.append("status_code = ?")
        params.append(status_code)
    if level:
        filters.append("level = ?")
        params.append(level.upper())
    if query:
        filters.append("query LIKE ?")
        params.append(f"%{query}%")
    if request_id:
        filters.append("request_id = ?")
        params.append(request_id)
    if start:
        filters.append("timestamp >= ?")
        params.append(start)
    if end:
        filters.append("timestamp <= ?")
        params.append(end)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    sql = f"""
        SELECT *
        FROM logs
        {where}
        ORDER BY timestamp DESC, id DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    with get_connection() as conn:
        return _rows_to_dicts(conn.execute(sql, params).fetchall())


def get_log_stats(
    *,
    microservice: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    init_db()
    filters = ["action IN ('request_end', 'request_error')"]
    params: list[Any] = []
    if microservice:
        filters.append("microservice = ?")
        params.append(normalize_microservice(microservice))
    if start:
        filters.append("timestamp >= ?")
        params.append(start)
    if end:
        filters.append("timestamp <= ?")
        params.append(end)

    where = f"WHERE {' AND '.join(filters)}"
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT microservice, status_code, latency_ms
            FROM logs
            {where}
            """,
            params,
        ).fetchall()
        lifecycle_rows = conn.execute(
            f"""
            SELECT request_id, action, microservice, timestamp
            FROM logs
            WHERE action IN ('request_start', 'request_end', 'request_error')
            {' AND microservice = ?' if microservice else ''}
            {' AND timestamp >= ?' if start else ''}
            {' AND timestamp <= ?' if end else ''}
            ORDER BY timestamp ASC, id ASC
            """,
            params,
        ).fetchall()

    latencies = sorted(
        float(row["latency_ms"]) for row in rows if row["latency_ms"] is not None
    )
    total = len(rows)
    errors = sum(
        1
        for row in rows
        if row["status_code"] is not None and int(row["status_code"]) >= 500
    )
    by_service: dict[str, dict[str, Any]] = {}
    for row in rows:
        service = row["microservice"]
        bucket = by_service.setdefault(
            service,
            {"requests": 0, "errors": 0, "latencies": []},
        )
        bucket["requests"] += 1
        if row["status_code"] is not None and int(row["status_code"]) >= 500:
            bucket["errors"] += 1
        if row["latency_ms"] is not None:
            bucket["latencies"].append(float(row["latency_ms"]))

    starts: dict[str, sqlite3.Row] = {}
    timestamp_latencies: list[float] = []
    timestamp_latencies_by_service: dict[str, list[float]] = {}
    for row in lifecycle_rows:
        request_id = row["request_id"]
        if not request_id:
            continue
        if row["action"] == "request_start":
            starts[request_id] = row
            continue
        start_row = starts.get(request_id)
        if not start_row:
            continue
        start_ts = datetime.fromisoformat(start_row["timestamp"])
        end_ts = datetime.fromisoformat(row["timestamp"])
        elapsed_ms = (end_ts - start_ts).total_seconds() * 1000
        if elapsed_ms < 0:
            continue
        timestamp_latencies.append(elapsed_ms)
        timestamp_latencies_by_service.setdefault(row["microservice"], []).append(elapsed_ms)

    def percentile(values: list[float], pct: float) -> float | None:
        if not values:
            return None
        idx = min(int(len(values) * pct), len(values) - 1)
        return round(values[idx], 2)

    services = {}
    for service, bucket in by_service.items():
        service_latencies = sorted(bucket["latencies"])
        count = bucket["requests"]
        services[service] = {
            "requests": count,
            "errors": bucket["errors"],
            "error_rate": round(bucket["errors"] / count, 4) if count else 0,
            "avg_latency_ms": round(sum(service_latencies) / len(service_latencies), 2)
            if service_latencies
            else None,
            "p95_latency_ms": percentile(service_latencies, 0.95),
            "p99_latency_ms": percentile(service_latencies, 0.99),
            "avg_latency_from_timestamps_ms": round(
                sum(timestamp_latencies_by_service.get(service, []))
                / len(timestamp_latencies_by_service.get(service, [])),
                2,
            )
            if timestamp_latencies_by_service.get(service)
            else None,
            "p95_latency_from_timestamps_ms": percentile(
                sorted(timestamp_latencies_by_service.get(service, [])), 0.95
            ),
            "p99_latency_from_timestamps_ms": percentile(
                sorted(timestamp_latencies_by_service.get(service, [])), 0.99
            ),
        }

    return {
        "requests": total,
        "errors": errors,
        "error_rate": round(errors / total, 4) if total else 0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "p95_latency_ms": percentile(latencies, 0.95),
        "p99_latency_ms": percentile(latencies, 0.99),
        "avg_latency_from_timestamps_ms": round(
            sum(timestamp_latencies) / len(timestamp_latencies), 2
        )
        if timestamp_latencies
        else None,
        "p95_latency_from_timestamps_ms": percentile(sorted(timestamp_latencies), 0.95),
        "p99_latency_from_timestamps_ms": percentile(sorted(timestamp_latencies), 0.99),
        "services": services,
    }

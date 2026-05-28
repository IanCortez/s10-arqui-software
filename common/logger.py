"""
Logger compartido por todos los microservicios.

Cada evento se escribe en una única base SQLite centralizada. Los requests HTTP
generan eventos `request_start` y `request_end`/`request_error` con el mismo
`request_id`, permitiendo calcular latencia por diferencia de timestamps y por
el campo `latency_ms`.
"""
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from common.log_store import insert_log


class StructuredFormatter(logging.Formatter):
    """Formato compacto para stdout durante desarrollo local."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds")
        module = getattr(record, "microservice", getattr(record, "mod", record.name))
        action = getattr(record, "action", record.getMessage())
        api = getattr(record, "api", "-")
        func = getattr(record, "fn", record.funcName)
        latency = getattr(record, "latency_ms", "-")
        status = getattr(record, "status", "-")
        query = getattr(record, "query", "-")
        msg = record.getMessage().replace("|", "/")
        return (
            f"{ts} | ACTION={action} | MODULE={module} | API={api} | FUNC={func} | "
            f"LEVEL={record.levelname} | STATUS={status} | LATENCY_MS={latency} | "
            f"QUERY={query} | MSG={msg}"
        )


class SQLiteLogHandler(logging.Handler):
    """Handler que persiste eventos estructurados en la base centralizada."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            status = getattr(record, "status", None)
            status_code = None
            try:
                status_code = int(status) if status is not None else None
            except (TypeError, ValueError):
                status_code = None

            latency = getattr(record, "latency_ms", None)
            try:
                latency_ms = float(latency) if latency not in (None, "-") else None
            except (TypeError, ValueError):
                latency_ms = None

            insert_log(
                {
                    "timestamp": datetime.fromtimestamp(
                        record.created, tz=timezone.utc
                    ).isoformat(timespec="milliseconds"),
                    "request_id": getattr(record, "request_id", None),
                    "action": getattr(record, "action", record.getMessage()),
                    "microservice": getattr(record, "microservice", getattr(record, "mod", record.name)),
                    "api": getattr(record, "api", None),
                    "function": getattr(record, "fn", record.funcName),
                    "level": record.levelname,
                    "status": str(status) if status is not None else None,
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                    "query": getattr(record, "query", None),
                    "message": record.getMessage(),
                    "metadata": getattr(record, "metadata", None),
                }
            )
        except Exception:
            self.handleError(record)


def get_logger(module_name: str) -> logging.Logger:
    """Devuelve un logger que escribe a SQLite y stdout."""
    logger = logging.getLogger(module_name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.addHandler(SQLiteLogHandler())

    ch = logging.StreamHandler()
    ch.setFormatter(StructuredFormatter())
    logger.addHandler(ch)

    return logger


def log_request_start(
    logger: logging.Logger,
    module: str,
    api: str,
    func: str,
    query: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Registra el inicio de un request HTTP y devuelve su request_id."""
    request_id = str(uuid4())
    logger.info(
        "request_start",
        extra={
            "request_id": request_id,
            "action": "request_start",
            "microservice": module,
            "api": api,
            "fn": func,
            "status": "STARTED",
            "query": query,
            "metadata": metadata,
        },
    )
    return request_id


@contextmanager
def log_block(
    logger: logging.Logger,
    module: str,
    api: str,
    func: str,
    request_id: str | None = None,
    query: str | None = None,
):
    """Mide latencia de un bloque interno de código."""
    start = time.perf_counter()
    ctx = {"status": "-"}
    logger.info(
        "block_start",
        extra={
            "request_id": request_id,
            "action": "block_start",
            "microservice": module,
            "api": api,
            "fn": func,
            "latency_ms": 0,
            "status": "STARTED",
            "query": query,
        },
    )
    try:
        yield ctx
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "block_end",
            extra={
                "request_id": request_id,
                "action": "block_end",
                "microservice": module,
                "api": api,
                "fn": func,
                "latency_ms": f"{elapsed:.2f}",
                "status": ctx["status"],
                "query": query,
            },
        )
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        logger.error(
            f"block_error: {e}",
            extra={
                "request_id": request_id,
                "action": "block_error",
                "microservice": module,
                "api": api,
                "fn": func,
                "latency_ms": f"{elapsed:.2f}",
                "status": "EXCEPTION",
                "query": query,
            },
        )
        raise


def log_request(
    logger: logging.Logger,
    module: str,
    api: str,
    func: str,
    latency_ms: float,
    status: int,
    msg: str = "request_done",
    request_id: str | None = None,
    query: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Registra el resultado final de un request HTTP."""
    is_error = status >= 400
    level = logger.error if is_error else logger.info
    level(
        msg,
        extra={
            "request_id": request_id,
            "action": "request_error" if is_error else "request_end",
            "microservice": module,
            "api": api,
            "fn": func,
            "latency_ms": f"{latency_ms:.2f}",
            "status": status,
            "query": query,
            "metadata": metadata,
        },
    )

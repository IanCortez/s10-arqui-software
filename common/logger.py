"""
Logger compartido por todos los microservicios.

Formato de log (una línea por evento):
{ISO_TIMESTAMP} | MODULE=<mod> | API=<api> | FUNC=<fn> | LEVEL=<lvl> | LATENCY_MS=<ms> | STATUS=<code> | MSG=<msg>

Provee:
- get_logger(module_name): logger con archivo dedicado en LOG_DIR.
- log_block(...): context manager para medir latencia de bloques de código
  (cumple el requisito "tiempo de inicio y fin de cada bloque de código").
"""
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)


class StructuredFormatter(logging.Formatter):
    """Pone todos los campos en una única línea parseable."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds")
        module = getattr(record, "mod", record.name)
        api = getattr(record, "api", "-")
        func = getattr(record, "fn", record.funcName)
        latency = getattr(record, "latency_ms", "-")
        status = getattr(record, "status", "-")
        # Aseguramos que MSG no rompa el parser si contiene "|"
        msg = record.getMessage().replace("|", "/")
        return (
            f"{ts} | MODULE={module} | API={api} | FUNC={func} | "
            f"LEVEL={record.levelname} | LATENCY_MS={latency} | "
            f"STATUS={status} | MSG={msg}"
        )


def get_logger(module_name: str) -> logging.Logger:
    """Devuelve un logger con archivo propio por microservicio."""
    logger = logging.getLogger(module_name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = StructuredFormatter()

    # Archivo dedicado por microservicio
    fh = logging.FileHandler(LOG_DIR / f"{module_name.lower()}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # También a stdout para debug local
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


@contextmanager
def log_block(logger: logging.Logger, module: str, api: str, func: str):
    """
    Context manager que mide tiempo de inicio y fin de un bloque de código.

    Uso:
        with log_block(logger, "SEARCH_API", "/poke/search", "call_poke_api") as ctx:
            r = requests.get(...)
            ctx["status"] = r.status_code
    """
    start = time.perf_counter()
    ctx = {"status": "-"}
    logger.info(
        "block_start",
        extra={"mod": module, "api": api, "fn": func, "latency_ms": 0, "status": "STARTED"},
    )
    try:
        yield ctx
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "block_end",
            extra={
                "mod": module,
                "api": api,
                "fn": func,
                "latency_ms": f"{elapsed:.2f}",
                "status": ctx["status"],
            },
        )
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        logger.error(
            f"block_error: {e}",
            extra={
                "mod": module,
                "api": api,
                "fn": func,
                "latency_ms": f"{elapsed:.2f}",
                "status": "EXCEPTION",
            },
        )
        raise


def log_request(logger: logging.Logger, module: str, api: str, func: str,
                latency_ms: float, status: int, msg: str = "request_done"):
    """Log de alto nivel para registrar el resultado final de un request HTTP."""
    level = logger.info if 200 <= status < 400 else logger.error
    level(
        msg,
        extra={
            "mod": module,
            "api": api,
            "fn": func,
            "latency_ms": f"{latency_ms:.2f}",
            "status": status,
        },
    )

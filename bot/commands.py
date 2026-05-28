"""
Comandos del Bot MonitorMach.
Cada comando opera sobre los logs ya parseados.
"""
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
from statistics import mean

from .log_parser import read_logs, request_records, normalize_module


# ---------- CheckLatency ----------
def check_latency(module: str, start: datetime, end: datetime) -> list[tuple[str, float]]:
    """Latencia promedio por día para un módulo en el rango [start, end]."""
    records = request_records(read_logs(module, start=start, end=end))
    by_day: dict[str, list[float]] = defaultdict(list)
    for r in records:
        if r["latency_ms"] is None:
            continue
        day = r["ts"].strftime("%d/%m")
        by_day[day].append(r["latency_ms"])

    return [(day, round(mean(values), 2)) for day, values in sorted(by_day.items())]


# ---------- CheckAvailability ----------
def check_availability(module: str, days: int) -> list[tuple[str, float]]:
    """
    Availability por día = #200 / (#200 + #500)
    Solo cuenta requests HTTP de entrada, no bloques internos.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    records = request_records(read_logs(module, start=start, end=end))

    by_day: dict[str, dict[int, int]] = defaultdict(lambda: {"ok": 0, "err": 0})
    for r in records:
        day = r["ts"].strftime("%d/%m")
        if r["status_int"] == 200:
            by_day[day]["ok"] += 1
        elif r["status_int"] >= 500:
            by_day[day]["err"] += 1

    result = []
    for day, counts in sorted(by_day.items()):
        total = counts["ok"] + counts["err"]
        avail = (counts["ok"] / total * 100) if total else 0.0
        result.append((day, round(avail, 2)))
    return result


# ---------- RenderGraph ----------
def render_graph(data: list[tuple[str, float]], title: str, unit: str = "") -> str:
    """Grafico de líneas ASCII estilo el use case del lab."""
    if not data:
        return f"\n  {title}\n  (sin datos)\n"

    labels = [d[0] for d in data]
    values = [d[1] for d in data]
    max_v = max(values)
    min_v = min(values)
    height = 10
    width_per_point = 6

    # Normaliza valores a filas
    span = max(max_v - min_v, 1)
    rows = []
    for h in range(height, 0, -1):
        line = []
        threshold = min_v + (span * h / height)
        for v in values:
            if v >= threshold:
                line.append("  *  ")
            else:
                line.append("     ")
        # Marcador del valor en su pico
        rows.append("".join(line))

    out = [f"\n  {title}\n"]
    # Etiquetas de valor a la izquierda (max y min)
    for i, row in enumerate(rows):
        if i == 0:
            out.append(f"{max_v:>8.1f}{unit} | {row}")
        elif i == height // 2:
            mid = (max_v + min_v) / 2
            out.append(f"{mid:>8.1f}{unit} | {row}")
        elif i == height - 1:
            out.append(f"{min_v:>8.1f}{unit} | {row}")
        else:
            out.append(f"{'':>8}   | {row}")
    out.append(f"{'':>8}   +" + "-" * (len(values) * width_per_point))
    out.append(f"{'':>11}" + "".join(f"{l:^{width_per_point}}" for l in labels))

    # También listamos valores exactos abajo (formato del use case)
    out.append("")
    for lbl, val in data:
        out.append(f"  {lbl}   **{val:.1f}{unit}**")
    return "\n".join(out)


# ---------- Stats ----------
def general_stats() -> dict:
    """Métricas agregadas globales."""
    records = request_records(read_logs())
    if not records:
        return {"error": "No hay logs disponibles. Corre Locust primero."}

    latencies = [r["latency_ms"] for r in records if r["latency_ms"] is not None]
    latencies_sorted = sorted(latencies)
    n = len(latencies_sorted)
    p95 = latencies_sorted[int(n * 0.95)] if n else 0
    p99 = latencies_sorted[int(n * 0.99)] if n else 0

    total = len(records)
    errors = sum(1 for r in records if r["status_int"] and r["status_int"] >= 500)
    error_ratio = errors / total if total else 0

    # Throughput: rango temporal real cubierto por los logs
    ts_min = min(r["ts"] for r in records)
    ts_max = max(r["ts"] for r in records)
    duration_s = max((ts_max - ts_min).total_seconds(), 1)
    rpm = total / duration_s * 60
    throughput = total / duration_s  # req/s

    # Top failing endpoint = combinación módulo+api con más errores
    fail_counter: Counter = Counter()
    for r in records:
        if r["status_int"] and r["status_int"] >= 500:
            fail_counter[f"{r['module']} {r['api']}"] += 1
    top_failing = fail_counter.most_common(1)[0] if fail_counter else ("(ninguno)", 0)

    # Latencia promedio por módulo (para identificar bottleneck)
    by_mod: dict[str, list[float]] = defaultdict(list)
    err_by_mod: dict[str, int] = defaultdict(int)
    total_by_mod: dict[str, int] = defaultdict(int)
    for r in records:
        total_by_mod[r["module"]] += 1
        if r["latency_ms"] is not None:
            by_mod[r["module"]].append(r["latency_ms"])
        if r["status_int"] and r["status_int"] >= 500:
            err_by_mod[r["module"]] += 1

    avg_by_mod = {m: round(mean(v), 2) for m, v in by_mod.items() if v}
    err_rate_by_mod = {
        m: round(err_by_mod[m] / total_by_mod[m], 3) for m in total_by_mod
    }

    return {
        "total_requests": total,
        "p95_latency_ms": round(p95, 2),
        "p99_latency_ms": round(p99, 2),
        "requests_per_minute": round(rpm, 2),
        "throughput_rps": round(throughput, 2),
        "error_ratio": round(error_ratio, 3),
        "top_failing_endpoint": top_failing,
        "avg_latency_by_module_ms": avg_by_mod,
        "error_rate_by_module": err_rate_by_mod,
    }


def analyze(stats: dict) -> dict:
    """Heurísticas para responder bottleneck / retry / scale."""
    if "error" in stats:
        return {}

    avg = stats["avg_latency_by_module_ms"]
    errs = stats["error_rate_by_module"]

    # Bottleneck = downstream con mayor latencia promedio.
    # Excluimos SEARCH_API porque es el orquestador y siempre va a ser el más lento
    # (su latencia = max de las latencias downstream + overhead).
    downstream = {m: v for m, v in avg.items() if m != "SEARCH_API"}
    bottleneck = max(downstream.items(), key=lambda x: x[1]) if downstream else (None, 0)

    # Retry = módulos con error_rate entre 2% y 20% (errores transitorios)
    retry_targets = [m for m, e in errs.items() if 0.02 <= e <= 0.20]

    # Scale = si p95 > 2000ms o throughput < target con muchos errores
    p95 = stats["p95_latency_ms"]
    err = stats["error_ratio"]
    scale = "Sí" if (p95 > 2000 or err > 0.15) else "No urgente"

    return {
        "bottleneck": f"{bottleneck[0]} con {bottleneck[1]} ms promedio" if bottleneck[0] else "n/a",
        "retry_recommended_for": retry_targets if retry_targets else ["(ninguno: errores muy altos o muy bajos)"],
        "should_scale": scale,
        "reasoning": (
            f"p95={p95}ms (umbral 2000ms), error_ratio={err:.1%} (umbral 15%). "
            "Retry sólo tiene sentido en módulos con errores transitorios (2-20%)."
        ),
    }

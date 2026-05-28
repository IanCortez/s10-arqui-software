"""
Bot - MonitorMach CLI

Uso:
    python -m bot.bot CheckLatency <module> <start-date> <end-date>
    python -m bot.bot CheckAvailability <module> -Last5Days
    python -m bot.bot RenderGraph -Latency <module> -Last5Days
    python -m bot.bot RenderGraph -Availability <module> -Last7Days
    python -m bot.bot Stats

Sin componentes de IA: solo parser de argumentos pre-definidos.
"""
import sys
from .commands import (
    check_latency, check_availability, render_graph,
    general_stats, analyze,
)
from .log_parser import parse_date, parse_window, normalize_module


BANNER = r"""
    <=======]}======
        --. /|
       _\"/_.'/
     .'._._,.'
    :/ \{}/
    (L /--',----._
     | \\
    snd Bot - MonitorMach
"""


def cmd_check_latency(args: list[str]):
    if len(args) < 3:
        print("Uso: CheckLatency <module> <start-date> <end-date>")
        sys.exit(1)
    module, start_s, end_s = args[0], args[1], args[2]
    start = parse_date(start_s)
    # end inclusivo hasta fin del día
    end = parse_date(end_s).replace(hour=23, minute=59, second=59)
    data = check_latency(module, start, end)

    print(f"\nCheckLatency {module} {start_s} {end_s}")
    if not data:
        print("(sin datos)")
        return
    for day, latency in data:
        print(f"  {day}   {latency:.0f}ms")


def cmd_check_availability(args: list[str]):
    if len(args) < 2:
        print("Uso: CheckAvailability <module> -[Last5Days|Last7Days]")
        sys.exit(1)
    module = args[0]
    window = args[1]
    start, end = parse_window(window)
    days = (end - start).days
    data = check_availability(module, days)

    print(f"\nCheckAvailability {module} {window}")
    if not data:
        print("(sin datos)")
        return
    for day, avail in data:
        print(f"  {day}   {avail:.1f}%")


def cmd_render_graph(args: list[str]):
    if len(args) < 3:
        print("Uso: RenderGraph -[Latency|Availability] <module> -[Last5Days|Last7Days]")
        sys.exit(1)
    metric_flag = args[0].lstrip("-").lower()
    module = args[1]
    window = args[2]

    if metric_flag == "latency":
        start, end = parse_window(window)
        data = check_latency(module, start, end)
        title = f"RenderGraph -Latency {module} {window}"
        unit = "ms"
    elif metric_flag == "availability":
        _, _ = parse_window(window)
        days = int(window.lstrip("-").lower().replace("last", "").replace("days", ""))
        data = check_availability(module, days)
        title = f"RenderGraph -Availability {module} {window}"
        unit = "%"
    else:
        print(f"Métrica desconocida: {metric_flag}")
        sys.exit(1)

    print(render_graph(data, title, unit))


def cmd_stats(args: list[str]):
    stats = general_stats()
    print("\n=== Stats Generales ===")
    if "error" in stats:
        print(stats["error"])
        return

    print(f"  Total requests:        {stats['total_requests']}")
    print(f"  P95 latency:           {stats['p95_latency_ms']} ms")
    print(f"  P99 latency:           {stats['p99_latency_ms']} ms")
    print(f"  Requests/minuto:       {stats['requests_per_minute']}")
    print(f"  Throughput:            {stats['throughput_rps']} req/s")
    print(f"  Error ratio:           {stats['error_ratio']:.1%}")
    print(f"  Top failing endpoint:  {stats['top_failing_endpoint'][0]} "
          f"({stats['top_failing_endpoint'][1]} fallas)")
    print("\n  Latencia promedio por módulo:")
    for mod, lat in stats["avg_latency_by_module_ms"].items():
        print(f"    {mod:<15} {lat} ms")
    print("\n  Error rate por módulo:")
    for mod, er in stats["error_rate_by_module"].items():
        print(f"    {mod:<15} {er:.1%}")

    analysis = analyze(stats)
    print("\n=== Análisis ===")
    print(f"  ¿Cuál es el bottleneck?    {analysis['bottleneck']}")
    print(f"  ¿Dónde retry?              {', '.join(analysis['retry_recommended_for'])}")
    print(f"  ¿Debe escalar?             {analysis['should_scale']}")
    print(f"  Razonamiento:              {analysis['reasoning']}")


COMMANDS = {
    "checklatency": cmd_check_latency,
    "checkavailability": cmd_check_availability,
    "rendergraph": cmd_render_graph,
    "stats": cmd_stats,
}


def main():
    if len(sys.argv) < 2:
        print(BANNER)
        print("\nComandos disponibles:")
        for c in COMMANDS:
            print(f"  - {c}")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]
    if cmd not in COMMANDS:
        print(f"Comando desconocido: {sys.argv[1]}")
        print(f"Disponibles: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    COMMANDS[cmd](args)


if __name__ == "__main__":
    main()

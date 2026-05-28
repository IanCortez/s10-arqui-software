# Bot - MonitorMach

Arquitectura de microservicios para monitorear latencia y disponibilidad, con bot CLI
que consume logs distribuidos para generar métricas.

## Arquitectura

```
                           ┌─────────────────┐
                           │   POKE_API      │  ──> pokeapi.co
                           │   (port 8001)   │
                           └─────────────────┘
                                   ▲
   POST /poke/search    ┌──────────┴──────────┐    ┌────────────────┐
   { Pokemon_Name }     │    SEARCH API       │    │   POKE_STATS   │
   ────────────────────▶│    (port 8000)      │──▶ │   (port 8002)  │──▶ SQLite
                        └──────────┬──────────┘    └────────────────┘
                                   │
                                   ▼               ┌────────────────┐
                                                   │   POKE_IMAGES  │
                                                   │   (port 8003)  │──▶ File mock
                                                   └────────────────┘
```

Cada microservicio escribe logs en `logs/<servicio>.log` con el formato:

```
{ISO_TIMESTAMP} | MODULE=<name> | API=<endpoint> | FUNC=<function> | LEVEL=<level> | LATENCY_MS=<ms> | STATUS=<code> | MSG=<message>
```

## Cómo correr

### Opción A — Docker Compose (recomendado)

```bash
docker compose up --build
```

### Opción B — Local con Python

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Seed de la base de stats
python services/poke_stats/seed_db.py

# 3. Levantar cada servicio en una terminal distinta
uvicorn services.poke_api.app:app --port 8001
uvicorn services.poke_stats.app:app --port 8002
uvicorn services.poke_images.app:app --port 8003
uvicorn services.search_api.app:app --port 8000
```

## Generación de carga (Locust)

```bash
locust -f load_tests/locustfile.py --headless -u 50 -r 5 -t 3m \
       --host http://localhost:8000
```

Esto genera entre 1.000 y 10.000 llamadas a `/poke/search`, creando logs reales en
los cuatro microservicios.

## Bot CLI

```bash
# Latencia
python -m bot.bot CheckLatency PokeImages 01/10 03/10

# Disponibilidad
python -m bot.bot CheckAvailability PokeStats -Last5Days

# Gráfico ASCII
python -m bot.bot RenderGraph -Latency PokeImages -Last7Days
python -m bot.bot RenderGraph -Availability PokeApi -Last5Days

# Stats generales + análisis (bottleneck / retry / scale)
python -m bot.bot Stats
```

Los módulos válidos son: `SearchApi`, `PokeApi`, `PokeStats`, `PokeImages`.

## Demo rápida sin Locust

Si solo quieres ver el bot funcionando sin levantar servicios ni Locust:

```bash
PYTHONPATH=. python scripts/seed_historical_logs.py
PYTHONPATH=. python -m bot.bot Stats
PYTHONPATH=. python -m bot.bot CheckLatency PokeImages 21/05 28/05
PYTHONPATH=. python -m bot.bot CheckAvailability PokeStats -Last5Days
PYTHONPATH=. python -m bot.bot RenderGraph -Latency PokeImages -Last7Days
PYTHONPATH=. python -m bot.bot RenderGraph -Availability PokeImages -Last5Days
```

El script `seed_historical_logs.py` simula 7 días de tráfico (~10.500 requests)
para que las gráficas tengan suficiente data. **No reemplaza a Locust** — es solo
una conveniencia para hacer demos rápidas; en producción los logs los generan los
microservicios reales.

## Resultados de ejecución

Las carpetas incluyen evidencia real de las pruebas:

- `screenshots/` — salidas (txt) de los 5 comandos del bot.
- `logs_sample/` — primeras y últimas 50 líneas de cada `*.log`, mostrando el formato.

Ejemplo del comando `Stats` corrido contra los logs:

```
=== Stats Generales ===
  Total requests:        42000
  P95 latency:           3956.07 ms
  Error ratio:           8.1%
  Top failing endpoint:  POKE_IMAGES /image/{name} (1249 fallas)

=== Análisis ===
  ¿Cuál es el bottleneck?    POKE_IMAGES con 2958.77 ms promedio
  ¿Debe escalar?             Sí
```

## Estructura del repo

```
monitor-mach/
├── common/logger.py             # Logger compartido + medición de bloques
├── services/
│   ├── search_api/              # Orquestador (puerto 8000)
│   ├── poke_api/                # Proxy a pokeapi.co (puerto 8001)
│   ├── poke_stats/              # SQLite con stats (puerto 8002)
│   └── poke_images/             # Mock de S3 (puerto 8003)
├── bot/
│   ├── bot.py                   # CLI entry point
│   ├── commands.py              # CheckLatency, CheckAvailability, RenderGraph, Stats
│   └── log_parser.py            # Parser del formato de logs
├── load_tests/locustfile.py     # Generador de carga 1k–10k requests
├── scripts/
│   ├── run_local.sh             # Arranque local sin Docker
│   └── seed_historical_logs.py  # Logs sintéticos para demos
├── docker-compose.yml
├── requirements.txt
├── screenshots/                 # Evidencia de ejecución del bot
└── logs_sample/                 # Muestras del formato de logs
```

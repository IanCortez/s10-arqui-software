# Bot - MonitorMach

Arquitectura de microservicios para monitorear latencia y disponibilidad, con bot CLI
que consume una base centralizada de logs para generar métricas.

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

Cada microservicio escribe eventos estructurados en una única base SQLite
centralizada (`data/central_logs.db` en Docker/local). Cada request HTTP genera:

- `request_start`: timestamp inicial, microservicio, endpoint, función y query.
- `request_end` o `request_error`: timestamp final, status, `latency_ms` y mensaje.
- `block_start`/`block_end`: mediciones internas para llamadas downstream, cache, DB, etc.

Campos principales: `timestamp`, `request_id`, `action`, `microservice`, `api`,
`function`, `level`, `status`, `status_code`, `latency_ms`, `query`, `message` y
`metadata_json`.

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
la base centralizada.

## Endpoints de logs

El Search API expone consultas sobre la base centralizada:

```bash
# Últimos 100 eventos
curl "http://localhost:8000/logs"

# Filtrar por microservicio, acción, query o status
curl "http://localhost:8000/logs?microservice=PokeImages&action=request_end&query=charizard"
curl "http://localhost:8000/logs?status_code=500&limit=50"

# Métricas de requests: avg/p95/p99 latency, latencia por timestamps, errores y error rate
curl "http://localhost:8000/logs/stats"
curl "http://localhost:8000/logs/stats?microservice=PokeApi"
```

La latencia se puede auditar de dos formas: por el campo `latency_ms` del evento
final y por la diferencia entre los timestamps de `request_start` y
`request_end`/`request_error` con el mismo `request_id`.

## Política de fallos

`/poke/search` trata `POKE_API` y `POKE_STATS` como dependencias obligatorias:
si cualquiera falla, el Search API corta la ejecución y responde `500`. Esos
`500` son fallos reales para JMeter, aunque provengan de la inyección controlada
de errores usada para generar métricas.

`POKE_IMAGES` es una dependencia opcional: si falla, el Search API mantiene la
respuesta exitosa y devuelve `"image": null`. El evento queda registrado como
`optional_dependency_failure`, pero no se cuenta como un request HTTP fallido.

## Prueba Docker + JMeter

La prueba automatizada levanta Docker, corre smoke tests, ejecuta JMeter y valida
el número exacto de muestras. Por defecto genera 2.000 llamadas y se niega a
correr menos de 2.000 o más de 10.000.

```bash
scripts/test_docker_jmeter.sh

# Parámetros opcionales
CALLS=4000 THREADS=20 scripts/test_docker_jmeter.sh
```

El plan JMeter espera HTTP `200`. Los `500` producidos por `POKE_API` o
`POKE_STATS` aparecen como failures en el `.jtl` y en el resumen.

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
en `data/central_logs.db` para que las gráficas tengan suficiente data. **No
reemplaza a Locust** — es solo una conveniencia para hacer demos rápidas; en
producción los logs los generan los microservicios reales.

## Resultados de ejecución

Las carpetas incluyen evidencia real de las pruebas:

- `screenshots/` — salidas (txt) de los 5 comandos del bot.
- `logs_sample/` — muestras históricas del formato anterior de archivos de log.

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
├── common/log_store.py          # SQLite centralizado + consultas/estadísticas
├── services/
│   ├── search_api/              # Orquestador (puerto 8000)
│   ├── poke_api/                # Proxy a pokeapi.co (puerto 8001)
│   ├── poke_stats/              # SQLite con stats (puerto 8002)
│   └── poke_images/             # Mock de S3 (puerto 8003)
├── bot/
│   ├── bot.py                   # CLI entry point
│   ├── commands.py              # CheckLatency, CheckAvailability, RenderGraph, Stats
│   └── log_parser.py            # Lector de la base centralizada
├── load_tests/locustfile.py     # Generador de carga 1k–10k requests
├── scripts/
│   ├── run_local.sh             # Arranque local sin Docker
│   └── seed_historical_logs.py  # Logs sintéticos para demos
├── docker-compose.yml
├── requirements.txt
├── screenshots/                 # Evidencia de ejecución del bot
└── logs_sample/                 # Muestras del formato de logs
```

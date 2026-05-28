#!/usr/bin/env bash
# Levanta los 4 microservicios localmente en background.
# Útil cuando no se usa Docker.
set -e

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
export LOG_DB_PATH="$PWD/data/central_logs.db"
mkdir -p "$(dirname "$LOG_DB_PATH")"

# Seed de la DB
python services/poke_stats/seed_db.py

echo "Levantando microservicios..."
uvicorn services.poke_api.app:app    --port 8001 > /tmp/poke_api.out    2>&1 &
echo "  poke-api    PID $!"
uvicorn services.poke_stats.app:app  --port 8002 > /tmp/poke_stats.out  2>&1 &
echo "  poke-stats  PID $!"
uvicorn services.poke_images.app:app --port 8003 > /tmp/poke_images.out 2>&1 &
echo "  poke-images PID $!"
sleep 1
uvicorn services.search_api.app:app  --port 8000 > /tmp/search_api.out  2>&1 &
echo "  search-api  PID $!"

echo ""
echo "Servicios corriendo. Logs DB en $LOG_DB_PATH"
echo "Probar: curl -X POST http://localhost:8000/poke/search -H 'Content-Type: application/json' -d '{\"Pokemon_Name\":\"charizard\"}'"
echo "Detener todo: pkill -f uvicorn"

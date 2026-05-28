#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

CALLS="${CALLS:-2000}"
THREADS="${THREADS:-20}"
RAMP="${RAMP:-10}"
JMETER_IMAGE="${JMETER_IMAGE:-justb4/jmeter:5.5}"
RESULT_DIR="${RESULT_DIR:-load_tests/results}"
RESULT_FILE="$RESULT_DIR/search_api_${CALLS}.jtl"
SUMMARY_FILE="$RESULT_DIR/search_api_${CALLS}_summary.txt"

if ! [[ "$CALLS" =~ ^[0-9]+$ ]]; then
  echo "CALLS must be an integer" >&2
  exit 2
fi

if (( CALLS < 2000 || CALLS > 10000 )); then
  echo "Refusing to run: CALLS must be between 2000 and 10000 inclusive. Got $CALLS." >&2
  exit 2
fi

if ! [[ "$THREADS" =~ ^[0-9]+$ ]] || (( THREADS < 1 || THREADS > CALLS )); then
  echo "THREADS must be an integer between 1 and CALLS" >&2
  exit 2
fi

if (( CALLS % THREADS != 0 )); then
  echo "CALLS must be divisible by THREADS so JMeter runs exactly CALLS samples." >&2
  echo "Got CALLS=$CALLS THREADS=$THREADS" >&2
  exit 2
fi

LOOPS=$((CALLS / THREADS))
mkdir -p "$RESULT_DIR"
rm -f "$RESULT_FILE" "$SUMMARY_FILE"

echo "== Docker build/start =="
docker compose up --build -d

echo "== Smoke tests inside Docker network =="
docker compose exec -T search-api python - <<'PY'
import json
import time
import urllib.request

checks = [
    ("search-api", "http://localhost:8000/health"),
    ("poke-api", "http://poke-api:8001/health"),
    ("poke-stats", "http://poke-stats:8002/health"),
    ("poke-images", "http://poke-images:8003/health"),
]

for name, url in checks:
    last_error = None
    for _ in range(30):
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                body = json.loads(response.read().decode("utf-8"))
            print(f"{name}: {body}")
            break
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    else:
        raise SystemExit(f"{name} health failed: {last_error}")

last_error = None
for _ in range(10):
    payload = json.dumps({"Pokemon_Name": "pikachu"}).encode("utf-8")
    request = urllib.request.Request(
        "http://localhost:8000/poke/search",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            print("search smoke:", response.status, response.read().decode("utf-8")[:240])
            break
    except urllib.error.HTTPError as exc:
        last_error = exc
        if exc.code != 500:
            raise
        time.sleep(1)
else:
    raise SystemExit(f"search smoke did not produce a 200 after retries: {last_error}")
PY

echo "== Log stats before JMeter =="
docker compose exec -T search-api python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://localhost:8000/logs/stats", timeout=10) as response:
    stats = json.loads(response.read().decode("utf-8"))
print(json.dumps(stats, indent=2, sort_keys=True))
PY

echo "== JMeter load test =="
echo "Calls: $CALLS  Threads: $THREADS  Loops/thread: $LOOPS  Ramp: $RAMP"
docker run --rm \
  --network s10-arqui-software_default \
  -v "$PWD/load_tests:/tests" \
  "$JMETER_IMAGE" \
  -n \
  -t /tests/search_api_2000.jmx \
  -l "/tests/results/$(basename "$RESULT_FILE")" \
  -j "/tests/results/jmeter_${CALLS}.log" \
  -Jhost=search-api \
  -Jport=8000 \
  -Jthreads="$THREADS" \
  -Jloops="$LOOPS" \
  -Jramp="$RAMP" | tee "$SUMMARY_FILE"

echo "== Validate JMeter sample count =="
python - <<PY
import csv
from pathlib import Path

expected = int("$CALLS")
path = Path("$RESULT_FILE")
with path.open(newline="") as fh:
    rows = list(csv.DictReader(fh))
actual = len(rows)
success = sum(1 for row in rows if row.get("success") == "true")
failures = actual - success
codes = {}
for row in rows:
    codes[row.get("responseCode", "")] = codes.get(row.get("responseCode", ""), 0) + 1
print(f"samples={actual}")
print(f"success={success}")
print(f"failures={failures}")
print(f"response_codes={codes}")
if actual != expected:
    raise SystemExit(f"Expected exactly {expected} samples, got {actual}")
PY

echo "== Log stats after JMeter =="
docker compose exec -T search-api python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://localhost:8000/logs/stats", timeout=10) as response:
    stats = json.loads(response.read().decode("utf-8"))
print(json.dumps(stats, indent=2, sort_keys=True))
PY

echo "== Recent centralized logs =="
docker compose exec -T search-api python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://localhost:8000/logs?limit=5", timeout=10) as response:
    logs = json.loads(response.read().decode("utf-8"))
print(json.dumps(logs, indent=2, sort_keys=True)[:4000])
PY

echo "Results:"
echo "  JTL: $RESULT_FILE"
echo "  Summary: $SUMMARY_FILE"

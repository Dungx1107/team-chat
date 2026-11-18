#!/bin/bash
# Đo Cache-Aside (cách A): Postgres local + giả lập độ trễ tới Supabase.
#
#   bash benchmark/experiments/05_cache_aside/run_all.sh
#
# Ma trận: kịch bản {rooms, rooms_mixed} x cache {tắt, bật} x LẶP lần, xen kẽ để
# giảm sai lệch theo thời gian. Mỗi lượt: tắt độ trễ -> seed lại -> dựng lại backend
# (cache rỗng) -> bật độ trễ -> đo thang 50 -> 2000. Kết quả vào results/.
set -u
cd "$(dirname "$0")/../../.."
COMPOSE="docker compose -f docker-compose.bench.yml"
R="$PWD/benchmark/experiments/05_cache_aside/results"
LATENCY_MS="${LATENCY_MS:-90}"
REPEATS="${REPEATS:-3}"
SCENARIOS="${SCENARIOS:-rooms rooms_mixed}"
mkdir -p "$R"
export MSYS_NO_PATHCONV=1

run_one() {   # $1 = kịch bản, $2 = true|false, $3 = lần
  local name="A_$1_cache-$2_r$3"
  echo "===== $name ($(date +%H:%M:%S)) ====="
  sh benchmark/shared/db_latency.sh 0 >/dev/null
  $COMPOSE run --rm backend python /benchmark/shared/seed_data.py 2>&1 | grep XONG
  BENCH_CACHE_ENABLED=$2 $COMPOSE up -d --force-recreate backend >/dev/null 2>&1
  sleep 8
  curl -sf localhost:8001/health >/dev/null || { echo "backend không lên"; return 1; }
  sh benchmark/shared/db_latency.sh "$LATENCY_MS" >/dev/null
  local start; start=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  ( while true; do
      docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}}" \
        teamchat_bench_backend teamchat_bench_db | sed "s/^/$(date +%H:%M:%S),/"
      sleep 5
    done ) > "$R/${name}_resources.csv" 2>&1 &
  local sp=$!

  python benchmark/run_load.py --scenario "$1" \
    --note "cach A: Postgres local + tre ${LATENCY_MS} ms, CACHE_ENABLED=$2, lan $3, 1 worker" \
    --out "$(cygpath -w "$R/${name}.json" 2>/dev/null || echo "$R/${name}.json")" \
    > "$R/${name}_console.txt" 2>&1

  kill "$sp" 2>/dev/null; wait "$sp" 2>/dev/null
  $COMPOSE logs backend --since "$start" --timestamps 2>&1 | gzip -9 > "$R/${name}_backend.log.gz"
  grep -E "=====|^->" "$R/${name}_console.txt"
}

for rep in $(seq 1 "$REPEATS"); do
  for scenario in $SCENARIOS; do
    for cache in false true; do
      run_one "$scenario" "$cache" "$rep"
    done
  done
done

sh benchmark/shared/db_latency.sh 0 >/dev/null
BENCH_CACHE_ENABLED=true $COMPOSE up -d --force-recreate backend >/dev/null 2>&1
echo "XONG TOAN BO ($(date +%H:%M:%S))"

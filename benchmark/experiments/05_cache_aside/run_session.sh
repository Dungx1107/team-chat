#!/bin/bash
# Đo Cache-Aside bằng kịch bản phiên dùng app thật (session), cách A:
# Postgres local + giả lập độ trễ tới Supabase.
#
#   bash benchmark/experiments/05_cache_aside/run_session.sh
#
# Mỗi lượt: tắt độ trễ -> seed lại -> dựng lại backend (cache rỗng) -> bật độ trễ ->
# đo thang 100 -> 2000 người (mỗi mức: 60 s mở app + 240 s chat). Kết quả vào results/.
set -u
cd "$(dirname "$0")/../../.."
COMPOSE="docker compose -f docker-compose.bench.yml"
R="$PWD/benchmark/experiments/05_cache_aside/results"
LATENCY_MS="${LATENCY_MS:-90}"
# nhãn:cache:ttl -- xen kẽ tắt/bật để giảm sai lệch theo thời gian
CONFIGS="${CONFIGS:-off:false:60 on60:true:60 off:false:60 on60:true:60 on600:true:600}"
mkdir -p "$R"
export MSYS_NO_PATHCONV=1

declare -A seen
for cfg in $CONFIGS; do
  IFS=: read -r label cache ttl <<< "$cfg"
  seen[$label]=$(( ${seen[$label]:-0} + 1 ))
  name="S_${label}_r${seen[$label]}"
  echo "===== $name ($(date +%H:%M:%S)) ====="

  sh benchmark/shared/db_latency.sh 0 >/dev/null
  $COMPOSE run --rm backend python /benchmark/shared/seed_data.py 2>&1 | grep XONG
  BENCH_CACHE_ENABLED=$cache BENCH_CACHE_TTL=$ttl $COMPOSE up -d --force-recreate backend >/dev/null 2>&1
  sleep 8
  curl -sf localhost:8001/health >/dev/null || { echo "backend không lên"; continue; }
  sh benchmark/shared/db_latency.sh "$LATENCY_MS" >/dev/null
  start=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  ( while true; do
      docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}}" \
        teamchat_bench_backend teamchat_bench_db | sed "s/^/$(date +%H:%M:%S),/"
      sleep 5
    done ) > "$R/${name}_resources.csv" 2>&1 &
  sp=$!

  python benchmark/run_load.py --scenario session \
    --note "session, cach A: Postgres local + tre ${LATENCY_MS} ms, CACHE_ENABLED=$cache, TTL=${ttl}s, 1 worker, lich su chat da sua N+1" \
    --out "$(cygpath -w "$R/${name}.json" 2>/dev/null || echo "$R/${name}.json")" \
    > "$R/${name}_console.txt" 2>&1

  kill "$sp" 2>/dev/null; wait "$sp" 2>/dev/null
  $COMPOSE logs backend --since "$start" --timestamps 2>&1 | gzip -9 > "$R/${name}_backend.log.gz"
  grep -E "=====|^->|NGHẼN|ổn \(|phục vụ hoàn toàn" "$R/${name}_console.txt"
done

sh benchmark/shared/db_latency.sh 0 >/dev/null
BENCH_CACHE_ENABLED=true $COMPOSE up -d --force-recreate backend >/dev/null 2>&1
echo "XONG TOAN BO ($(date +%H:%M:%S))"

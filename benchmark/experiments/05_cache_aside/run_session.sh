#!/bin/bash
# Đo bằng kịch bản phiên dùng app thật (session), cách A: Postgres local + giả lập
# độ trễ tới Supabase.
#
#   bash benchmark/experiments/05_cache_aside/run_session.sh
#   CONFIGS="b:new:false:redis:4" bash .../run_session.sh     # chạy riêng một cấu hình
#
# Mỗi cấu hình "nhãn:lịch_sử:cache:backend_cache:số_worker":
#   lịch_sử = old (MessageRepository trước 794b709, N+1) | new (đã sửa)
# Mỗi lượt: tắt độ trễ -> seed lại -> xóa cache Redis -> dựng lại backend -> bật độ
# trễ -> đo thang 100 -> 2000 người (mỗi mức 60 s mở app + 240 s chat).
set -u
cd "$(dirname "$0")/../../.."
COMPOSE="docker compose -f docker-compose.bench.yml"
R="$PWD/benchmark/experiments/05_cache_aside/results"
LATENCY_MS="${LATENCY_MS:-90}"
TTL="${TTL:-60}"
CONFIGS="${CONFIGS:-a:old:false:redis:4 b:new:false:redis:4 c:new:true:redis:4}"
REPO_FILE=backend/app/repositories/message_repo.py
mkdir -p "$R"
export MSYS_NO_PATHCONV=1

restore_repo() { git checkout -q HEAD -- "$REPO_FILE"; }
trap restore_repo EXIT

for cfg in $CONFIGS; do
  IFS=: read -r label history cache cache_backend workers <<< "$cfg"
  name="S2_${label}_hist-${history}_cache-${cache}_w${workers}"
  echo "===== $name ($(date +%H:%M:%S)) ====="

  if [ "$history" = "old" ]; then
    git show 794b709^:"$REPO_FILE" > "$REPO_FILE"
  else
    restore_repo
  fi

  sh benchmark/shared/db_latency.sh 0 >/dev/null
  # Sau một mức tải quá sức, backend còn request treo giữ khóa bảng: TRUNCATE của seed
  # sẽ chờ mãi. Dừng backend và cắt mọi kết nối còn sót trước khi seed.
  $COMPOSE stop -t 5 backend >/dev/null 2>&1
  docker exec teamchat_bench_db psql -U postgres -d teamchat_bench -qtAc \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'teamchat_bench' AND pid <> pg_backend_pid()" >/dev/null
  $COMPOSE run --rm backend python /benchmark/shared/seed_data.py 2>&1 | grep XONG
  docker exec teamchat_bench_redis redis-cli -n 1 FLUSHDB >/dev/null
  BENCH_WORKERS=$workers BENCH_CACHE_ENABLED=$cache BENCH_CACHE_BACKEND=$cache_backend BENCH_CACHE_TTL=$TTL \
    $COMPOSE up -d --force-recreate backend >/dev/null 2>&1
  for i in $(seq 1 30); do curl -sf localhost:8001/health >/dev/null && break; sleep 2; done
  curl -sf localhost:8001/health >/dev/null || { echo "backend không lên"; continue; }
  sh benchmark/shared/db_latency.sh "$LATENCY_MS" >/dev/null
  start=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  ( while true; do
      docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}}" \
        teamchat_bench_backend teamchat_bench_db teamchat_bench_redis | sed "s/^/$(date +%H:%M:%S),/"
      sleep 5
    done ) > "$R/${name}_resources.csv" 2>&1 &
  sp=$!

  python benchmark/run_load.py --scenario session \
    --note "session, cach A: Postgres local + tre ${LATENCY_MS} ms, lich su chat=$history, CACHE_ENABLED=$cache ($cache_backend, TTL ${TTL}s), $workers worker, be ket noi 20+30/worker" \
    --out "$(cygpath -w "$R/${name}.json" 2>/dev/null || echo "$R/${name}.json")" \
    > "$R/${name}_console.txt" 2>&1

  kill "$sp" 2>/dev/null; wait "$sp" 2>/dev/null
  $COMPOSE logs backend --since "$start" --timestamps 2>&1 | gzip -9 > "$R/${name}_backend.log.gz"
  grep -E "=====|^->|NGHẼN|ổn \(|phục vụ" "$R/${name}_console.txt"
done

restore_repo
sh benchmark/shared/db_latency.sh 0 >/dev/null
echo "XONG TOAN BO ($(date +%H:%M:%S))"

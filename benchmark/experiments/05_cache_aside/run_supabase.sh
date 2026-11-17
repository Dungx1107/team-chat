#!/bin/bash
# Cách B: đo kịch bản session trên một project Supabase RIÊNG (không phải project chính),
# để xác nhận kết quả giả lập độ trễ của cách A.
#
#   1. Tạo project Supabase riêng, cùng vùng với project chính
#   2. Thêm vào .env:  BENCH_DATABASE_URL=<chuỗi Session pooler, cổng 5432>
#   3. bash benchmark/experiments/05_cache_aside/run_supabase.sh
#
# Supabase gói miễn phí cho ~15 kết nối qua session pooler, nên chạy 1 worker với bể
# 10 + 5 = 15 kết nối -- đúng điều kiện của các lượt cách A S_off / S_on60.
# Seed XÓA SẠCH project đo; seed_data.py từ chối nếu địa chỉ trùng project chính.
set -u
cd "$(dirname "$0")/../../.."
COMPOSE="docker compose -f docker-compose.bench.yml"
R="$PWD/benchmark/experiments/05_cache_aside/results"
STEPS="${STEPS:-100 200 500}"
CONFIGS="${CONFIGS:-off:false on:true}"
export MSYS_NO_PATHCONV=1

# Đọc từ .env mà không in ra màn hình
read -r BENCH_BACKEND_DATABASE_URL BENCH_PROD_DB_REF < <(python - <<'EOF'
from urllib.parse import urlparse
env = {}
for line in open(".env", encoding="utf-8"):
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.rstrip("\n").split("=", 1)
        env[k.strip()] = v.strip().strip('"')
bench, prod = env.get("BENCH_DATABASE_URL", ""), env.get("DATABASE_URL", "")
bench_ref = (urlparse(bench).username or "").split(".")[-1]
prod_ref = (urlparse(prod).username or "").split(".")[-1]
if not bench or not prod_ref or bench_ref == prod_ref:
    raise SystemExit("thiếu BENCH_DATABASE_URL hoặc nó trùng project chính")
print(bench, prod_ref)
EOF
) || { echo "Dừng: kiểm tra BENCH_DATABASE_URL trong .env"; exit 1; }
export BENCH_BACKEND_DATABASE_URL BENCH_PROD_DB_REF
export BENCH_ALLOW_REMOTE_DB=1 BENCH_WORKERS=1 BENCH_DB_POOL_SIZE=10 BENCH_DB_MAX_OVERFLOW=5
sh benchmark/shared/db_latency.sh 0 >/dev/null   # độ trễ lúc này là mạng thật

for cfg in $CONFIGS; do
  IFS=: read -r label cache <<< "$cfg"
  name="B_supabase_cache-${label}_w1"
  echo "===== $name ($(date +%H:%M:%S)) ====="

  $COMPOSE stop -t 5 backend >/dev/null 2>&1
  $COMPOSE run --rm backend python /benchmark/shared/seed_data.py 2>&1 | grep -E "XONG|TỪ CHỐI|Error"
  docker exec teamchat_bench_redis redis-cli -n 1 FLUSHDB >/dev/null
  BENCH_CACHE_ENABLED=$cache BENCH_CACHE_BACKEND=redis $COMPOSE up -d --force-recreate backend >/dev/null 2>&1
  for i in $(seq 1 30); do curl -sf localhost:8001/health >/dev/null && break; sleep 2; done
  curl -sf localhost:8001/health >/dev/null || { echo "backend không lên"; continue; }
  start=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  ( while true; do
      docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}}" \
        teamchat_bench_backend teamchat_bench_redis | sed "s/^/$(date +%H:%M:%S),/"
      sleep 5
    done ) > "$R/${name}_resources.csv" 2>&1 &
  sp=$!

  python benchmark/run_load.py --scenario session --steps $STEPS \
    --note "session, cach B: Supabase that (project rieng, Seoul, session pooler), lich su chat da sua, CACHE_ENABLED=$cache (redis), 1 worker, be 10+5" \
    --out "$(cygpath -w "$R/${name}.json" 2>/dev/null || echo "$R/${name}.json")" \
    > "$R/${name}_console.txt" 2>&1

  kill "$sp" 2>/dev/null; wait "$sp" 2>/dev/null
  # Log có thể chứa địa chỉ máy chủ DB nhưng không có mật khẩu (SQLAlchemy che mật khẩu)
  $COMPOSE logs backend --since "$start" --timestamps 2>&1 | gzip -9 > "$R/${name}_backend.log.gz"
  grep -E "=====|^->|NGHẼN|ổn \(|phục vụ" "$R/${name}_console.txt"
done

# Trả môi trường đo về DB local
unset BENCH_BACKEND_DATABASE_URL BENCH_ALLOW_REMOTE_DB BENCH_PROD_DB_REF BENCH_DB_POOL_SIZE BENCH_DB_MAX_OVERFLOW
$COMPOSE stop -t 5 backend >/dev/null 2>&1
echo "XONG TOAN BO ($(date +%H:%M:%S))"

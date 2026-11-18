#!/bin/sh
# Giả lập độ trễ mạng giữa backend và DB của môi trường đo, để đo như khi DB ở xa
# (Supabase). Độ trễ thêm vào mỗi gói tin DB gửi đi, tức cộng thẳng vào mỗi lượt đi về.
#
#   sh benchmark/shared/db_latency.sh 90   # thêm 90 ms
#   sh benchmark/shared/db_latency.sh 0    # bỏ giả lập
#
# Tắt giả lập trước khi seed, nếu không seed sẽ rất chậm.
set -e
MS="${1:?Dùng: db_latency.sh <mili giây>}"
C=teamchat_bench_db
docker exec "$C" sh -c 'command -v tc >/dev/null || apk add --no-cache -q iproute2-tc'
docker exec "$C" tc qdisc del dev eth0 root 2>/dev/null || true
if [ "$MS" != "0" ]; then
  docker exec "$C" tc qdisc add dev eth0 root netem delay "${MS}ms"
fi
docker exec "$C" tc qdisc show dev eth0

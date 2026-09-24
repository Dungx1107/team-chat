#!/bin/sh
# Sinh chứng chỉ tự ký nếu chưa có.
#
# Trình duyệt chỉ cho truy cập micro/camera trên localhost hoặc HTTPS, nên muốn
# gọi video giữa hai thiết bị trong mạng LAN thì bắt buộc phải có HTTPS.
# Chứng chỉ được giữ trong volume, nên chỉ phải chấp nhận cảnh báo một lần.
set -e

CERT_DIR=/etc/nginx/certs
CRT="$CERT_DIR/server.crt"
KEY="$CERT_DIR/server.key"

mkdir -p "$CERT_DIR"
if [ -f "$CRT" ] && [ -f "$KEY" ]; then
  echo "[cert] Dùng chứng chỉ có sẵn"
  exit 0
fi

SAN="DNS:localhost,IP:127.0.0.1"
# CERT_IPS: danh sách IP LAN, cách nhau bằng dấu phẩy, ví dụ 192.168.8.73
for ip in $(echo "${CERT_IPS:-}" | tr ',' ' '); do
  SAN="$SAN,IP:$ip"
done

echo "[cert] Sinh chứng chỉ tự ký cho: $SAN"
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout "$KEY" -out "$CRT" \
  -subj "/CN=team-chat.local" \
  -addext "subjectAltName=$SAN" >/dev/null 2>&1

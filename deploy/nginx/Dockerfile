FROM nginx:1.27-alpine

# openssl để tự sinh chứng chỉ tự ký lần đầu khởi động
RUN apk add --no-cache openssl

COPY nginx.conf /etc/nginx/conf.d/default.conf
# Ảnh nginx chính thức tự chạy mọi script trong /docker-entrypoint.d trước khi khởi động
COPY 10-gen-cert.sh /docker-entrypoint.d/10-gen-cert.sh
RUN chmod +x /docker-entrypoint.d/10-gen-cert.sh

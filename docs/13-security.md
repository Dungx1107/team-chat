# 13. Security

## Current implementation

- Password hash qua Passlib/bcrypt; password raw không lưu trong DB.
- Access JWT ký HS256 và kiểm tra trong `AuthenticationMiddleware`.
- Refresh token random, backend lưu SHA-256 hash và rotate khi refresh.
- Service kiểm tra room membership/role cho room, message, attachment và call.
- Pydantic schema validate request; message tối đa 4000, attachment 25 MB, avatar 5 MB.
- `LocalFileStorage` dùng UUID filename và chống path traversal.
- `ui.js.escapeHtml()` escape dữ liệu trước khi đưa vào HTML.
- Nginx redirect HTTP->HTTPS; certificate hiện là self-signed.
- WebSocket yêu cầu access token query parameter và kiểm tra subscribe/call action.

## Security considerations

Đây là các điểm cần cân nhắc, không phải cơ chế đã triển khai:

1. `jwt.py` hardcode access lifetime 60 phút; setting `ACCESS_TOKEN_EXPIRE_MINUTES` không có hiệu lực.
2. Query-string token có thể xuất hiện trong log/proxy history; có thể cân nhắc cơ chế handshake/header phù hợp.
3. Self-signed certificate gây cảnh báo và không thay thế certificate tin cậy production.
4. Presence/event state chỉ in-memory; nhiều backend instance cần broker đồng bộ.
5. `create_all()` không thay thế migration có version.
6. Upload ghi hết stream trước khi domain kiểm tra size; cần streaming limit nếu muốn từ chối sớm.
7. `MAX_UPLOAD_BYTES` trong settings không điều khiển giới hạn hardcode 25 MB.
8. CORS/CSRF policy riêng biệt không được xác định trong source; cần kiểm chứng thêm trước khi public deployment.
9. Không thấy virus scanning, object storage policy hay TURN authentication trong repository.

Không nên mô tả các cải thiện trên như tính năng hiện tại.

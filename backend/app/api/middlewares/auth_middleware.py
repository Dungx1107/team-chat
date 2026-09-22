import re
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.infra.security.jwt import decode_access_token

# Các đường dẫn không cần đăng nhập
PUBLIC_PATHS = (
    "/docs",
    "/redoc",
    "/api/openapi.json",
    "/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/ws",
)

# Ảnh đại diện để công khai, vì thẻ <img> của trình duyệt
# không gửi kèm được header Authorization.
PUBLIC_PATTERNS = (
    re.compile(r"^/api/users/\d+/avatar/?$"),
    re.compile(r"^/api/rooms/\d+/avatar/?$"),
)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Chốt xác thực tập trung cho toàn bộ API.

    Nhờ đặt ở tầng middleware, không endpoint nào phải tự viết lại
    việc kiểm tra token -- đúng yêu cầu "không viết lặp trong từng endpoint".
    """

    def _is_public(self, path: str) -> bool:
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return True
        return any(p.match(path) for p in PUBLIC_PATTERNS)

    async def dispatch(self, request: Request, call_next):
        # WebSocket không đi qua HTTP middleware
        if request.scope["type"] == "websocket":
            return await call_next(request)

        # Trình duyệt gửi preflight OPTIONS trước request thật, cho qua ngay
        if request.method == "OPTIONS":
            return await call_next(request)

        if self._is_public(request.url.path):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Yêu cầu đăng nhập (Thiếu Bearer Token)"}
            )

        token = auth_header.split(" ", 1)[1].strip()
        payload = decode_access_token(token)

        if not payload or "sub" not in payload:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token không hợp lệ hoặc đã hết hạn"}
            )

        # Gắn danh tính đã xác thực vào request để các endpoint dùng lại
        request.state.user_id = int(payload["sub"])
        return await call_next(request)

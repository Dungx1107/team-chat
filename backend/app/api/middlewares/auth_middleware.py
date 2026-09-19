from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.infra.security.jwt import decode_access_token

PUBLIC_PATHS = [
    "/docs",
    "/api/openapi.json",
    "/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
]

class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Cho phép các path công khai đi qua mà không cần xác thực
        if any(request.url.path.startswith(path) for path in PUBLIC_PATHS):
            return await call_next(request)

        # 2. Kiểm tra header Authorization
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Yêu cầu đăng nhập (Thiếu Bearer Token)"}
            )

        token = auth_header.split(" ")[1]
        payload = decode_access_token(token)

        # 3. Kiểm tra tính hợp lệ và hạn của Token
        if not payload or "sub" not in payload:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token không hợp lệ hoặc đã hết hạn"}
            )

        # 4. Gắn user_id đã xác thực vào context của request
        request.state.user_id = int(payload["sub"])
        return await call_next(request)

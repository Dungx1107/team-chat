from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from app.config import settings
from app.infra.db.session import engine, Base
import app.infra.db.models

from app.api.routers import auth_router, rooms_router, messages_router
from app.infra.security.jwt import decode_access_token

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/api/openapi.json",
    docs_url="/docs"
)

# 1. Khai báo CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATHS = [
    "/docs",
    "/api/openapi.json",
    "/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
]

# 2. Xử lý xác thực
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Cho qua ngay lập tức mọi request OPTIONS của trình duyệt
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if any(path.startswith(p) for p in PUBLIC_PATHS):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Yêu cầu đăng nhập (Thiếu Bearer Token)"}
        )

    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)

    if not payload or "sub" not in payload:
        return JSONResponse(
            status_code=401,
            content={"detail": "Token không hợp lệ hoặc đã hết hạn"}
        )

    request.state.user_id = int(payload["sub"])
    return await call_next(request)

# 3. Đăng ký Routers
app.include_router(auth_router, prefix="/api")
app.include_router(rooms_router, prefix="/api")
app.include_router(messages_router, prefix="/api")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "team-chat-api"}

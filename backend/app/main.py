import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.infra.db.session import engine, Base
import app.infra.db.models  # noqa: F401  -- nạp bảng vào metadata

from app.api.middlewares.auth_middleware import AuthenticationMiddleware
from app.api.routers import (
    auth_router,
    rooms_router,
    messages_router,
    users_router,
    ws_router,
)
from app.infra.realtime.connection_manager import connection_manager

logging.basicConfig(level=logging.INFO)

Base.metadata.create_all(bind=engine)

# Thư mục lưu tệp tải lên, gắn với Docker volume
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API dịch vụ chat nội bộ: phòng công khai/riêng tư, phân quyền, tệp đính kèm, biểu cảm và realtime qua WebSocket.",
    version="2.0.0",
    openapi_url="/api/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)


# 1. Xác thực tập trung
app.add_middleware(AuthenticationMiddleware)

# 2. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# 3. Routers
app.include_router(auth_router, prefix="/api")
app.include_router(rooms_router, prefix="/api")
app.include_router(messages_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(ws_router)  # /ws không nằm dưới /api


@app.on_event("startup")
async def on_startup():
    """Gắn event loop chính cho bộ phát sự kiện.

    Các endpoint đồng bộ chạy trong threadpool nên không tự có event loop;
    ConnectionManager cần tham chiếu này để đẩy sự kiện WebSocket ra ngoài.
    """
    connection_manager.bind_loop(asyncio.get_running_loop())
    logging.info("Team Chat API đã sẵn sàng, realtime đang bật")
    logging.info("CORS origins cho phép: %s", settings.cors_origin_list)


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "service": "team-chat-api",
        "version": "2.0.0",
        "online_users": len(connection_manager.online_user_ids()),
    }

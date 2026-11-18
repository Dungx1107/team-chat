from fastapi import Depends, Request, HTTPException, status
from sqlalchemy.orm import Session
from app.config import settings
from app.infra.db.session import get_db

# Repositories
from app.repositories.user_repo import UserRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.room_repo import RoomRepository
from app.repositories.message_repo import (
    MessageRepository,
    AttachmentRepository,
    ReactionRepository,
)

# Infrastructure adapters
from app.infra.storage.supabase_storage import SupabaseFileStorage
from app.infra.storage.local_storage import LocalFileStorage
from app.infra.realtime.connection_manager import connection_manager
from app.infra.cache.memory_cache import InMemoryCache
from app.infra.cache.redis_cache import RedisCache

# Đường đọc (CQRS mức nhẹ) và Cache-Aside
from app.queries.room_queries import IRoomQueries, RoomQueries, CachedRoomQueries
from app.queries.cache_invalidation import RoomCacheInvalidator

# Services
from app.services.auth_service import AuthService
from app.services.room_service import RoomService
from app.services.message_service import MessageService
from app.services.user_service import UserService
from app.services.call_service import CallService
from app.repositories.call_repo import CallRepository


# Bộ nhớ lưu trữ dùng chung, khởi tạo một lần
if settings.STORAGE_BACKEND == "local":
    file_storage = LocalFileStorage(settings.UPLOAD_DIR)
else:
    file_storage = SupabaseFileStorage(
        supabase_url=settings.SUPABASE_URL,
        supabase_key=settings.SUPABASE_SERVICE_ROLE_KEY,
        bucket_name=settings.SUPABASE_STORAGE_BUCKET,
    )

# Cache dùng chung cho cả tiến trình. Bật cache thì mọi Service phát sự kiện qua
# RoomCacheInvalidator: nó xóa key liên quan rồi chuyển tiếp cho WebSocket.
# Nhiều worker thì bắt buộc CACHE_BACKEND=redis: bản trong RAM mỗi worker một bản,
# worker này xóa cache thì worker kia vẫn trả dữ liệu cũ.
if not settings.CACHE_ENABLED:
    room_cache = None
elif settings.CACHE_BACKEND == "redis":
    room_cache = RedisCache(settings.REDIS_URL)
else:
    room_cache = InMemoryCache()
event_publisher = (
    RoomCacheInvalidator(connection_manager, room_cache) if room_cache else connection_manager
)

# Lấy User ID đã được Auth Middleware xác thực sẵn
def get_current_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Người dùng chưa được xác thực"
        )
    return user_id


# --- Dependency Injection cho Tầng Service ---
# Service chỉ nhận các interface, không biết gì về SQLAlchemy hay WebSocket.

def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(db), RefreshTokenRepository(db))


def get_room_service(db: Session = Depends(get_db)) -> RoomService:
    return RoomService(
        room_repo=RoomRepository(db),
        user_repo=UserRepository(db),
        event_publisher=event_publisher,
        file_storage=file_storage,
    )


def get_message_service(db: Session = Depends(get_db)) -> MessageService:
    return MessageService(
        message_repo=MessageRepository(db),
        room_repo=RoomRepository(db),
        attachment_repo=AttachmentRepository(db),
        reaction_repo=ReactionRepository(db),
        file_storage=file_storage,
        event_publisher=event_publisher,
    )


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db), file_storage=file_storage, event_publisher=event_publisher)


def get_call_service(db: Session = Depends(get_db)) -> CallService:
    return CallService(
        call_repo=CallRepository(db),
        room_repo=RoomRepository(db),
        user_repo=UserRepository(db),
        event_publisher=event_publisher,
    )


# --- Đường đọc ---

def get_room_queries(db: Session = Depends(get_db)) -> IRoomQueries:
    queries = RoomQueries(RoomRepository(db))
    if room_cache:
        return CachedRoomQueries(queries, room_cache, settings.CACHE_TTL_SECONDS)
    return queries

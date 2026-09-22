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
from app.infra.storage.local_storage import LocalFileStorage
from app.infra.realtime.connection_manager import connection_manager

# Services
from app.services.auth_service import AuthService
from app.services.room_service import RoomService
from app.services.message_service import MessageService
from app.services.user_service import UserService


# Bộ nhớ lưu trữ dùng chung, khởi tạo một lần
file_storage = LocalFileStorage(settings.UPLOAD_DIR)


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
        event_publisher=connection_manager,
        file_storage=file_storage,
    )


def get_message_service(db: Session = Depends(get_db)) -> MessageService:
    return MessageService(
        message_repo=MessageRepository(db),
        room_repo=RoomRepository(db),
        attachment_repo=AttachmentRepository(db),
        reaction_repo=ReactionRepository(db),
        file_storage=file_storage,
        event_publisher=connection_manager,
    )


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db), file_storage=file_storage, event_publisher=connection_manager)

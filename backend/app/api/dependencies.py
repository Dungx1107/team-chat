from fastapi import Depends, Request, HTTPException, status
from sqlalchemy.orm import Session
from app.infra.db.session import get_db

# Repositories
from app.repositories.user_repo import UserRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.room_repo import RoomRepository
from app.repositories.message_repo import MessageRepository

# Services
from app.services.auth_service import AuthService
from app.services.room_service import RoomService
from app.services.message_service import MessageService

# Lấy User ID đã được Auth Middleware xác thực sẵn
def get_current_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Người dùng chưa được xác thực"
        )
    return user_id

# Dependency Injection cho Tầng Service
def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    user_repo = UserRepository(db)
    refresh_token_repo = RefreshTokenRepository(db)
    return AuthService(user_repo, refresh_token_repo)

def get_room_service(db: Session = Depends(get_db)) -> RoomService:
    room_repo = RoomRepository(db)
    return RoomService(room_repo)

def get_message_service(db: Session = Depends(get_db)) -> MessageService:
    message_repo = MessageRepository(db)
    room_repo = RoomRepository(db)
    return MessageService(message_repo, room_repo)

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from app.domain.interfaces import IUserRepository, IRefreshTokenRepository
from app.domain.models import User, RefreshToken
from app.infra.security.password import hash_password, verify_password
from app.infra.security.jwt import create_access_token, generate_refresh_token, hash_token

class AuthService:
    def __init__(self, user_repo: IUserRepository, refresh_token_repo: IRefreshTokenRepository):
        self.user_repo = user_repo
        self.refresh_token_repo = refresh_token_repo

    def register(self, email: str, username: str, password: str, first_name: str, last_name: str) -> User:
        if self.user_repo.get_by_email(email):
            raise ValueError("Email đã tồn tại trên hệ thống")
        if self.user_repo.get_by_username(username):
            raise ValueError("Username đã được sử dụng")

        new_user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            first_name=first_name,
            last_name=last_name
        )
        return self.user_repo.create(new_user)

    def login(self, email: str, password: str) -> Dict[str, Any]:
        user = self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("Email hoặc mật khẩu không chính xác")
        if not user.is_active:
            raise ValueError("Tài khoản đã bị vô hiệu hóa")

        # Cấp cặp Access Token và Refresh Token
        access_token = create_access_token(subject=user.id)
        raw_refresh_token = generate_refresh_token()

        refresh_entity = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh_token),
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        self.refresh_token_repo.create(refresh_entity)

        return {
            "access_token": access_token,
            "refresh_token": raw_refresh_token,
            "token_type": "bearer",
            "user": user
        }

    def rotate_refresh_token(self, raw_refresh_token: str) -> Dict[str, Any]:
        t_hash = hash_token(raw_refresh_token)
        token_record = self.refresh_token_repo.get_by_token_hash(t_hash)

        if not token_record:
            raise ValueError("Refresh Token không hợp lệ")

        # Phát hiện Token đã bị thu hồi mà vẫn cố dùng -> Dấu hiệu bị đánh cắp -> Thu hồi toàn bộ
        if token_record.is_revoked:
            self.refresh_token_repo.revoke_all_user_tokens(token_record.user_id)
            raise ValueError("Token đã bị thu hồi trước đó. Phát hiện truy cập trái phép.")

        if token_record.is_expired():
            raise ValueError("Refresh Token đã hết hạn, vui lòng đăng nhập lại")

        # Thu hồi token hiện tại (Rotation)
        self.refresh_token_repo.revoke_token(t_hash)

        # Cấp cặp mới
        new_access_token = create_access_token(subject=token_record.user_id)
        new_raw_refresh_token = generate_refresh_token()
        new_refresh_entity = RefreshToken(
            user_id=token_record.user_id,
            token_hash=hash_token(new_raw_refresh_token),
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        self.refresh_token_repo.create(new_refresh_entity)

        return {
            "access_token": new_access_token,
            "refresh_token": new_raw_refresh_token,
            "token_type": "bearer"
        }

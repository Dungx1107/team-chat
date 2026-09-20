from datetime import datetime
from typing import Optional

class User:
    def __init__(
        self,
        email: str,
        username: str,
        password_hash: str,
        first_name: str,
        last_name: str,
        id: Optional[int] = None,
        is_active: bool = True,
        avatar_url: Optional[str] = None,
        bio: Optional[str] = None,
        status: Optional[str] = None,
        created_at: Optional[datetime] = None
    ):
        self.id = id
        self.email = email
        self.username = username
        self.password_hash = password_hash
        self.first_name = first_name
        self.last_name = last_name
        self.is_active = is_active
        self.avatar_url = avatar_url
        self.bio = bio
        self.status = status
        self.created_at = created_at or datetime.utcnow()

    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}".strip()

    @property
    def initials(self) -> str:
        """Chữ cái đầu dùng làm avatar mặc định khi chưa tải ảnh lên."""
        parts = [p for p in (self.first_name, self.last_name) if p]
        if not parts:
            return (self.username[:1] or "?").upper()
        return "".join(p.strip()[0].upper() for p in parts[:2])

    def update_profile(
        self,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        bio: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        if first_name is not None:
            if not first_name.strip():
                raise ValueError("Tên không được để trống")
            self.first_name = first_name.strip()
        if last_name is not None:
            if not last_name.strip():
                raise ValueError("Họ không được để trống")
            self.last_name = last_name.strip()
        if bio is not None:
            if len(bio) > 500:
                raise ValueError("Giới thiệu không được vượt quá 500 ký tự")
            self.bio = bio.strip() or None
        if status is not None:
            if len(status) > 100:
                raise ValueError("Trạng thái không được vượt quá 100 ký tự")
            self.status = status.strip() or None

    def set_avatar(self, url: Optional[str]) -> None:
        self.avatar_url = url

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

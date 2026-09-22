from typing import BinaryIO, List, Optional
from app.domain.interfaces import IUserRepository, IFileStorage, IEventPublisher
from app.domain.models import User


class UserService:
    """Nghiệp vụ hồ sơ người dùng."""

    ALLOWED_AVATAR_TYPES = (
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    )
    MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5MB

    def __init__(self, user_repo: IUserRepository, file_storage: Optional[IFileStorage] = None, event_publisher: Optional[IEventPublisher] = None):
        self.user_repo = user_repo
        self.file_storage = file_storage
        self.events = event_publisher

    def get_profile(self, user_id: int) -> User:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("Người dùng không tồn tại")
        return user

    def update_profile(
        self,
        user_id: int,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        bio: Optional[str] = None,
        status: Optional[str] = None,
    ) -> User:
        user = self.get_profile(user_id)
        # Toàn bộ luật kiểm tra nằm trong entity User
        user.update_profile(first_name=first_name, last_name=last_name, bio=bio, status=status)
        updated = self.user_repo.update(user)
        self._publish_updated(updated)
        return updated

    def update_avatar(
        self,
        user_id: int,
        file_obj: BinaryIO,
        filename: str,
        content_type: str,
    ) -> User:
        if not self.file_storage:
            raise ValueError("Chức năng tải ảnh chưa được cấu hình")
        if content_type not in self.ALLOWED_AVATAR_TYPES:
            raise ValueError("Ảnh đại diện chỉ chấp nhận định dạng JPEG, PNG, GIF hoặc WEBP")

        user = self.get_profile(user_id)
        old_avatar = user.avatar_url

        stored_name, size_bytes = self.file_storage.save(file_obj, filename)
        if size_bytes > self.MAX_AVATAR_BYTES:
            self.file_storage.delete(stored_name)
            raise ValueError("Ảnh đại diện không được vượt quá 5MB")

        user.set_avatar(stored_name)
        updated = self.user_repo.update(user)

        # Xóa ảnh cũ để không tích rác trên volume
        if old_avatar and old_avatar != stored_name:
            self.file_storage.delete(old_avatar)

        self._publish_updated(updated)
        return updated

    def _publish_updated(self, user: User) -> None:
        if self.events:
            self.events.publish_to_user_rooms(user.id, "user.updated", {"user": {
                "id": user.id,
                "full_name": user.full_name,
                "avatar_url": user.avatar_url,
                "bio": user.bio,
                "status": user.status,
            }})

    def search_users(self, keyword: str, limit: int = 20) -> List[User]:
        if not keyword or not keyword.strip():
            return []
        return self.user_repo.search(keyword, limit=limit)

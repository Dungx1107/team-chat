from datetime import datetime
from typing import Optional

class Room:
    def __init__(
        self,
        name: str,
        owner_id: int,
        id: Optional[int] = None,
        description: Optional[str] = None,
        is_private: bool = False,
        avatar_url: Optional[str] = None,
        created_at: Optional[datetime] = None
    ):
        if not name or len(name.strip()) == 0:
            raise ValueError("Tên phòng không được để trống")
        self.id = id
        self.name = name.strip()
        self.owner_id = owner_id
        self.description = (description or "").strip() or None
        self.is_private = is_private
        self.avatar_url = avatar_url
        self.created_at = created_at or datetime.utcnow()

    def is_owner(self, user_id: int) -> bool:
        return self.owner_id == user_id

    def is_visible_to_public(self) -> bool:
        """Phòng công khai hiện trong danh sách chung, phòng riêng tư thì không."""
        return not self.is_private

    def rename(self, new_name: str) -> None:
        if not new_name or len(new_name.strip()) == 0:
            raise ValueError("Tên phòng không được để trống")
        self.name = new_name.strip()

from datetime import datetime
from typing import Optional

class Message:
    def __init__(
        self,
        room_id: int,
        user_id: int,
        content: str,
        id: Optional[int] = None,
        created_at: Optional[datetime] = None,
        sender_name: Optional[str] = None,
        username: Optional[str] = None,
    ):
        if not content or len(content.strip()) == 0:
            raise ValueError("Nội dung tin nhắn không được để trống")
        self.id = id
        self.room_id = room_id
        self.user_id = user_id
        self.content = content
        self.created_at = created_at or datetime.utcnow()
        self.sender_name = sender_name
        self.username = username

    def is_sent_by(self, user_id: int) -> bool:
        return self.user_id == user_id
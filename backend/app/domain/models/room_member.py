from datetime import datetime
from typing import Optional

class RoomMember:
    ROLE_OWNER = "OWNER"
    ROLE_MEMBER = "MEMBER"

    def __init__(
        self,
        room_id: int,
        user_id: int,
        role: str = ROLE_MEMBER,
        id: Optional[int] = None,
        joined_at: Optional[datetime] = None
    ):
        self.id = id
        self.room_id = room_id
        self.user_id = user_id
        self.role = role
        self.joined_at = joined_at or datetime.utcnow()

    def is_owner(self) -> bool:
        return self.role == self.ROLE_OWNER

from datetime import datetime
from typing import Optional

class Room:
    def __init__(
        self,
        name: str,
        owner_id: int,
        id: Optional[int] = None,
        created_at: Optional[datetime] = None
    ):
        if not name or len(name.strip()) == 0:
            raise ValueError("Tên phòng không được để trống")
        self.id = id
        self.name = name.strip()
        self.owner_id = owner_id
        self.created_at = created_at or datetime.utcnow()

    def is_owner(self, user_id: int) -> bool:
        return self.owner_id == user_id

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
        created_at: Optional[datetime] = None
    ):
        self.id = id
        self.email = email
        self.username = username
        self.password_hash = password_hash
        self.first_name = first_name
        self.last_name = last_name
        self.is_active = is_active
        self.created_at = created_at or datetime.utcnow()

    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}".strip()

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

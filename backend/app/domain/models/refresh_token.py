from datetime import datetime
from typing import Optional

class RefreshToken:
    def __init__(
        self,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        id: Optional[int] = None,
        is_revoked: bool = False,
        created_at: Optional[datetime] = None
    ):
        self.id = id
        self.user_id = user_id
        self.token_hash = token_hash
        self.expires_at = expires_at
        self.is_revoked = is_revoked
        self.created_at = created_at or datetime.utcnow()

    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expires_at

    def revoke(self) -> None:
        self.is_revoked = True

    def is_valid(self) -> bool:
        return not self.is_revoked and not self.is_expired()

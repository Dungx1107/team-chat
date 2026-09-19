from abc import ABC, abstractmethod
from typing import Optional
from app.domain.models import RefreshToken

class IRefreshTokenRepository(ABC):
    @abstractmethod
    def create(self, refresh_token: RefreshToken) -> RefreshToken:
        pass

    @abstractmethod
    def get_by_token_hash(self, token_hash: str) -> Optional[RefreshToken]:
        pass

    @abstractmethod
    def revoke_token(self, token_hash: str) -> None:
        pass

    @abstractmethod
    def revoke_all_user_tokens(self, user_id: int) -> None:
        pass

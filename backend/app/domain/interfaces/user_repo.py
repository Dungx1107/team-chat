from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.models import User

class IUserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[User]:
        pass

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[User]:
        pass

    @abstractmethod
    def get_by_username(self, username: str) -> Optional[User]:
        pass

    @abstractmethod
    def create(self, user: User) -> User:
        pass

    @abstractmethod
    def update(self, user: User) -> User:
        pass

    @abstractmethod
    def search(self, keyword: str, limit: int = 20) -> List[User]:
        """Tìm người dùng theo username/email/họ tên, phục vụ việc mời vào phòng riêng tư."""
        pass

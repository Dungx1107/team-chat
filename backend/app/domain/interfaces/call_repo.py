from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.models import Call


class ICallRepository(ABC):
    @abstractmethod
    def create(self, call: Call) -> Call:
        """Lưu cuộc gọi kèm toàn bộ người tham gia."""
        pass

    @abstractmethod
    def get_by_id(self, call_id: int) -> Optional[Call]:
        pass

    @abstractmethod
    def save(self, call: Call) -> Call:
        """Ghi lại trạng thái cuộc gọi và trạng thái từng người tham gia."""
        pass

    @abstractmethod
    def find_open_call_of_user(self, user_id: int) -> Optional[Call]:
        """Cuộc gọi đang đổ chuông hoặc đang diễn ra mà người này tham gia."""
        pass

    @abstractmethod
    def list_by_user(self, user_id: int, limit: int = 30) -> List[Call]:
        pass

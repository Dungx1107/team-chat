from abc import ABC, abstractmethod
from typing import List
from app.domain.models import Message

class IMessageRepository(ABC):
    @abstractmethod
    def create(self, message: Message) -> Message:
        pass

    @abstractmethod
    def get_by_room_id(self, room_id: int, limit: int = 50, offset: int = 0) -> List[Message]:
        pass

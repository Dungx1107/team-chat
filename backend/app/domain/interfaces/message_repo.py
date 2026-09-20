from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.models import Message, Attachment, Reaction

class IMessageRepository(ABC):
    @abstractmethod
    def create(self, message: Message) -> Message:
        pass

    @abstractmethod
    def get_by_id(self, message_id: int) -> Optional[Message]:
        pass

    @abstractmethod
    def get_by_room_id(self, room_id: int, limit: int = 50, offset: int = 0) -> List[Message]:
        """Tin nhắn của phòng, đã kèm sẵn thông tin người gửi, tệp và biểu cảm."""
        pass

    @abstractmethod
    def update(self, message: Message) -> Message:
        pass

    @abstractmethod
    def soft_delete(self, message_id: int) -> bool:
        pass


class IAttachmentRepository(ABC):
    @abstractmethod
    def create(self, attachment: Attachment) -> Attachment:
        pass

    @abstractmethod
    def get_by_id(self, attachment_id: int) -> Optional[Attachment]:
        pass


class IReactionRepository(ABC):
    @abstractmethod
    def add(self, reaction: Reaction) -> Reaction:
        pass

    @abstractmethod
    def remove(self, message_id: int, user_id: int, emoji: str) -> bool:
        pass

    @abstractmethod
    def get(self, message_id: int, user_id: int, emoji: str) -> Optional[Reaction]:
        pass

    @abstractmethod
    def list_by_message(self, message_id: int) -> List[Reaction]:
        pass

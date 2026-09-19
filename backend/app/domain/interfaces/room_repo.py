from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.models import Room, RoomMember

class IRoomRepository(ABC):
    @abstractmethod
    def create(self, room: Room) -> Room:
        pass

    @abstractmethod
    def get_by_id(self, room_id: int) -> Optional[Room]:
        pass

    @abstractmethod
    def list_all(self, limit: int = 50, offset: int = 0) -> List[Room]:
        pass

    @abstractmethod
    def delete(self, room_id: int) -> bool:
        pass

    @abstractmethod
    def add_member(self, member: RoomMember) -> RoomMember:
        pass

    @abstractmethod
    def get_member(self, room_id: int, user_id: int) -> Optional[RoomMember]:
        pass

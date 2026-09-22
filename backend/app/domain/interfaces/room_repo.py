from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from app.domain.models import Room, RoomMember, User

class IRoomRepository(ABC):
    @abstractmethod
    def create(self, room: Room) -> Room:
        pass

    @abstractmethod
    def get_by_id(self, room_id: int) -> Optional[Room]:
        pass

    @abstractmethod
    def update(self, room: Room) -> Room:
        pass

    @abstractmethod
    def list_all(self, limit: int = 50, offset: int = 0) -> List[Room]:
        """Chỉ trả về các phòng công khai."""
        pass

    @abstractmethod
    def list_visible_to_user(self, user_id: int, limit: int = 50, offset: int = 0) -> List[Room]:
        """Phòng công khai + phòng riêng tư mà người dùng là thành viên."""
        pass

    @abstractmethod
    def delete(self, room_id: int) -> bool:
        pass

    # --- Thành viên ---

    @abstractmethod
    def add_member(self, member: RoomMember) -> RoomMember:
        pass

    @abstractmethod
    def get_member(self, room_id: int, user_id: int) -> Optional[RoomMember]:
        pass

    @abstractmethod
    def list_members(self, room_id: int) -> List[Tuple[RoomMember, User]]:
        """Danh sách thành viên kèm thông tin hồ sơ của từng người."""
        pass

    @abstractmethod
    def update_member_role(self, room_id: int, user_id: int, role: str) -> Optional[RoomMember]:
        pass

    @abstractmethod
    def remove_member(self, room_id: int, user_id: int) -> bool:
        pass

    @abstractmethod
    def count_members(self, room_id: int) -> int:
        pass

    @abstractmethod
    def get_last_message_summary(self, room_id: int) -> Optional[dict]:
        pass

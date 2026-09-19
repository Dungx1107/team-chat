from typing import List
from app.domain.interfaces import IRoomRepository
from app.domain.models import Room, RoomMember

class RoomService:
    def __init__(self, room_repo: IRoomRepository):
        self.room_repo = room_repo

    def create_room(self, name: str, owner_id: int) -> Room:
        new_room = Room(name=name, owner_id=owner_id)
        created_room = self.room_repo.create(new_room)

        # Tự động gán người tạo làm OWNER của phòng
        owner_member = RoomMember(
            room_id=created_room.id,
            user_id=owner_id,
            role=RoomMember.ROLE_OWNER
        )
        self.room_repo.add_member(owner_member)
        return created_room

    def list_rooms(self, limit: int = 50, offset: int = 0) -> List[Room]:
        return self.room_repo.list_all(limit=limit, offset=offset)

    def delete_room(self, room_id: int, user_id: int) -> bool:
        room = self.room_repo.get_by_id(room_id)
        if not room:
            raise ValueError("Phòng chat không tồn tại")
        
        # Áp dụng nghiệp vụ đóng gói trong Entity Room
        if not room.is_owner(user_id):
            raise PermissionError("Bạn không có quyền xóa phòng này (chỉ chủ phòng mới được xóa)")

        return self.room_repo.delete(room_id)

    def join_room(self, room_id: int, user_id: int) -> RoomMember:
        room = self.room_repo.get_by_id(room_id)
        if not room:
            raise ValueError("Phòng chat không tồn tại")

        existing_member = self.room_repo.get_member(room_id, user_id)
        if existing_member:
            return existing_member

        new_member = RoomMember(room_id=room_id, user_id=user_id, role=RoomMember.ROLE_MEMBER)
        return self.room_repo.add_member(new_member)

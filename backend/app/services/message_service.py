from typing import List
from app.domain.interfaces import IMessageRepository, IRoomRepository
from app.domain.models import Message, RoomMember

class MessageService:
    def __init__(self, message_repo: IMessageRepository, room_repo: IRoomRepository):
        self.message_repo = message_repo
        self.room_repo = room_repo

    def send_message(self, room_id: int, user_id: int, content: str) -> Message:
        room = self.room_repo.get_by_id(room_id)
        if not room:
            raise ValueError("Phòng chat không tồn tại")

        # Tự động cho tham gia phòng nếu chưa là thành viên
        member = self.room_repo.get_member(room_id, user_id)
        if not member:
            new_member = RoomMember(room_id=room_id, user_id=user_id)
            self.room_repo.add_member(new_member)

        # Entity Message tự kiểm tra content không được rỗng
        new_message = Message(room_id=room_id, user_id=user_id, content=content)
        return self.message_repo.create(new_message)

    def get_room_messages(self, room_id: int, limit: int = 50, offset: int = 0) -> List[Message]:
        room = self.room_repo.get_by_id(room_id)
        if not room:
            raise ValueError("Phòng chat không tồn tại")
        return self.message_repo.get_by_room_id(room_id=room_id, limit=limit, offset=offset)

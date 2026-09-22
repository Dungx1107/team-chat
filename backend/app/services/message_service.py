from datetime import datetime
from typing import BinaryIO, List, Optional
from app.domain.interfaces import (
    IMessageRepository,
    IRoomRepository,
    IAttachmentRepository,
    IReactionRepository,
    IFileStorage,
    IEventPublisher,
)
from app.domain.interfaces.event_publisher import NullEventPublisher
from app.domain.models import Message, Attachment, Reaction, RoomMember


class MessageService:
    """Nghiệp vụ tin nhắn: gửi, đọc, xóa, đính kèm tệp và biểu cảm."""

    def __init__(
        self,
        message_repo: IMessageRepository,
        room_repo: IRoomRepository,
        attachment_repo: Optional[IAttachmentRepository] = None,
        reaction_repo: Optional[IReactionRepository] = None,
        file_storage: Optional[IFileStorage] = None,
        event_publisher: Optional[IEventPublisher] = None,
    ):
        self.message_repo = message_repo
        self.room_repo = room_repo
        self.attachment_repo = attachment_repo
        self.reaction_repo = reaction_repo
        self.file_storage = file_storage
        self.events = event_publisher or NullEventPublisher()

    # ---------- Kiểm tra quyền ----------

    def _require_room(self, room_id: int):
        room = self.room_repo.get_by_id(room_id)
        if not room:
            raise ValueError("Phòng chat không tồn tại")
        return room

    def _require_membership(self, room_id: int, user_id: int) -> RoomMember:
        """Mọi thao tác với tin nhắn đều đòi hỏi là thành viên của phòng.

        Đây là chốt chặn bảo mật: trước đây ai đăng nhập cũng đọc được
        tin nhắn của mọi phòng, kể cả phòng riêng tư.
        """
        member = self.room_repo.get_member(room_id, user_id)
        if not member:
            raise PermissionError("Bạn không phải thành viên của phòng này")
        return member

    def _ensure_member_for_public_room(self, room_id: int, user_id: int) -> RoomMember:
        """Phòng công khai: tự động tham gia. Phòng riêng tư: phải được mời."""
        member = self.room_repo.get_member(room_id, user_id)
        if member:
            return member

        room = self._require_room(room_id)
        if room.is_private:
            raise PermissionError("Đây là phòng riêng tư, bạn cần được mời mới vào được")

        return self.room_repo.add_member(
            RoomMember(room_id=room_id, user_id=user_id, role=RoomMember.ROLE_MEMBER)
        )

    # ---------- Gửi và đọc tin nhắn ----------

    def send_message(self, room_id: int, user_id: int, content: str, reply_to_id: Optional[int] = None) -> Message:
        self._require_room(room_id)
        self._ensure_member_for_public_room(room_id, user_id)

        if reply_to_id is not None:
            reply = self.message_repo.get_by_id(reply_to_id)
            if not reply or reply.room_id != room_id:
                raise ValueError("Tin nhắn trả lời phải thuộc cùng phòng")
        new_message = Message(room_id=room_id, user_id=user_id, content=content, reply_to_id=reply_to_id)
        created = self.message_repo.create(new_message)

        self.events.publish_to_room(room_id, "message.created", {"message": self._to_payload(created)})
        self.events.publish_to_room(room_id, "room.summary_updated", {
            "room_id": room_id, "last_message": self._to_payload(created),
        })
        return created

    def send_file_message(
        self,
        room_id: int,
        user_id: int,
        file_obj: BinaryIO,
        filename: str,
        content_type: str,
        caption: str = "",
    ) -> Message:
        if not self.file_storage or not self.attachment_repo:
            raise ValueError("Chức năng đính kèm tệp chưa được cấu hình")

        self._require_room(room_id)
        self._ensure_member_for_public_room(room_id, user_id)

        stored_name, size_bytes = self.file_storage.save(file_obj, filename)

        try:
            # Entity tự kiểm tra dung lượng và tính hợp lệ
            attachment = Attachment(
                filename=filename,
                stored_name=stored_name,
                content_type=content_type,
                size_bytes=size_bytes,
                uploaded_by=user_id,
            )
        except ValueError:
            # Tệp không hợp lệ thì phải dọn file vừa ghi, tránh rác trên đĩa
            self.file_storage.delete(stored_name)
            raise

        saved_attachment = self.attachment_repo.create(attachment)

        message = Message(
            room_id=room_id,
            user_id=user_id,
            content=caption or "",
            message_type=Message.TYPE_FILE,
            attachment_id=saved_attachment.id,
        )
        created = self.message_repo.create(message)

        self.events.publish_to_room(room_id, "message.created", {"message": self._to_payload(created)})
        self.events.publish_to_room(room_id, "room.summary_updated", {
            "room_id": room_id, "last_message": self._to_payload(created),
        })
        return created

    def get_room_messages(
        self, room_id: int, user_id: int, limit: int = 50, offset: int = 0
    ) -> List[Message]:
        self._require_room(room_id)
        self._require_membership(room_id, user_id)
        return self.message_repo.get_by_room_id(room_id=room_id, limit=limit, offset=offset)

    def delete_message(self, message_id: int, user_id: int) -> bool:
        message = self.message_repo.get_by_id(message_id)
        if not message:
            raise ValueError("Tin nhắn không tồn tại")

        member = self._require_membership(message.room_id, user_id)

        # Tự xóa tin của mình, hoặc là quản trị viên/chủ phòng xóa tin người khác
        if not message.is_sent_by(user_id) and not member.can_moderate_messages():
            raise PermissionError("Bạn chỉ được xóa tin nhắn của chính mình")

        deleted = self.message_repo.soft_delete(message_id)
        if deleted:
            self.events.publish_to_room(message.room_id, "message.deleted", {
                "message_id": message_id,
                "room_id": message.room_id,
                "deleted_by": user_id,
            })
        return deleted

    def get_attachment(self, attachment_id: int, user_id: int) -> Attachment:
        """Lấy metadata tệp. Người tải phải là thành viên phòng chứa tệp đó."""
        if not self.attachment_repo:
            raise ValueError("Chức năng đính kèm tệp chưa được cấu hình")

        attachment = self.attachment_repo.get_by_id(attachment_id)
        if not attachment:
            raise ValueError("Tệp không tồn tại")
        room_id = self.attachment_repo.get_message_room_id(attachment_id)
        if room_id is None:
            raise ValueError("Tệp không còn gắn với tin nhắn")
        self._require_membership(room_id, user_id)
        return attachment

    def edit_message(self, message_id: int, user_id: int, content: str) -> Message:
        message = self.message_repo.get_by_id(message_id)
        if not message:
            raise ValueError("Tin nhắn không tồn tại")
        self._require_membership(message.room_id, user_id)
        if not message.is_sent_by(user_id):
            raise PermissionError("Bạn chỉ được chỉnh sửa tin nhắn của chính mình")
        message.edit(content)
        updated = self.message_repo.update(message)
        self.events.publish_to_room(updated.room_id, "message.updated", {"message": self._to_payload(updated)})
        return updated

    def set_pinned(self, message_id: int, user_id: int, pinned: bool) -> Message:
        message = self.message_repo.get_by_id(message_id)
        if not message:
            raise ValueError("Tin nhắn không tồn tại")
        member = self._require_membership(message.room_id, user_id)
        if not member.can_moderate_messages():
            raise PermissionError("Chỉ OWNER hoặc ADMIN mới được ghim tin nhắn")
        updated = self.message_repo.set_pinned(message_id, pinned, user_id)
        if not updated:
            raise ValueError("Tin nhắn không tồn tại")
        self.events.publish_to_room(message.room_id, "message.pinned", {
            "type": "message.pinned",
            "message_id": message.id, "room_id": message.room_id,
            "pinned": pinned, "pinned_by": user_id,
            "pinned_at": updated.pinned_at,
            "message": self._to_payload(updated),
        })
        return updated

    def pin_message(self, message_id: int, user_id: int) -> Message:
        return self.set_pinned(message_id, user_id, True)

    def unpin_message(self, message_id: int, user_id: int) -> Message:
        return self.set_pinned(message_id, user_id, False)

    def get_pinned_messages(self, room_id: int, user_id: int) -> List[Message]:
        self._require_room(room_id)
        self._require_membership(room_id, user_id)
        return self.message_repo.get_pinned_by_room_id(room_id)

    # ---------- Biểu cảm ----------

    def toggle_reaction(self, message_id: int, user_id: int, emoji: str) -> dict:
        """Thả biểu cảm; nếu đã thả rồi thì gỡ ra (hành vi giống Slack/Discord)."""
        if not self.reaction_repo:
            raise ValueError("Chức năng biểu cảm chưa được cấu hình")

        message = self.message_repo.get_by_id(message_id)
        if not message:
            raise ValueError("Tin nhắn không tồn tại")

        self._require_membership(message.room_id, user_id)

        existing = self.reaction_repo.get(message_id, user_id, emoji)
        if existing:
            self.reaction_repo.remove(message_id, user_id, emoji)
            action = "removed"
        else:
            # Entity Reaction tự chặn emoji không nằm trong danh sách cho phép
            self.reaction_repo.add(Reaction(message_id=message_id, user_id=user_id, emoji=emoji))
            action = "added"

        reactions = self.reaction_repo.list_by_message(message_id)
        payload = {
            "message_id": message_id,
            "room_id": message.room_id,
            "action": "add" if action == "added" else "remove",
            "user_id": user_id,
            "emoji": emoji,
            "reactions": self._summarize_reactions(reactions),
        }
        self.events.publish_to_room(message.room_id, "message.reaction", payload)
        return payload

    # ---------- Chuyển đổi dữ liệu cho sự kiện realtime ----------

    @staticmethod
    def _summarize_reactions(reactions: List[Reaction]) -> List[dict]:
        """Gom biểu cảm theo emoji: mỗi loại kèm số lượng và ai đã thả."""
        grouped: dict = {}
        for r in reactions:
            entry = grouped.setdefault(r.emoji, {"emoji": r.emoji, "count": 0, "user_ids": []})
            entry["count"] += 1
            entry["user_ids"].append(r.user_id)
        return list(grouped.values())

    def _to_payload(self, message: Message) -> dict:
        data = {
            "id": message.id,
            "room_id": message.room_id,
            "user_id": message.user_id,
            "sender_id": message.user_id,
            "type": message.message_type,
            "content": message.content,
            "message_type": message.message_type,
            "created_at": message.created_at,
            "edited_at": message.edited_at,
            "is_deleted": message.is_deleted,
            "sender_name": message.sender_name,
            "username": message.username,
            "avatar_url": message.avatar_url,
            "reactions": self._summarize_reactions(message.reactions),
            "attachment": None,
            "sender": {
                "id": message.user_id,
                "full_name": message.sender_name,
                "avatar_url": message.avatar_url,
            },
            "reply_to_id": getattr(message, "reply_to_id", None),
            "forwarded_from_id": getattr(message, "forwarded_from_id", None),
            "pinned": getattr(message, "pinned", False),
            "pinned_at": getattr(message, "pinned_at", None),
            "pinned_by": getattr(message, "pinned_by", None),
            "deleted_at": getattr(message, "deleted_at", None),
        }
        if message.attachment:
            a = message.attachment
            data["attachment"] = {
                "id": a.id,
                "filename": a.filename,
                "content_type": a.content_type,
                "size_bytes": a.size_bytes,
                "kind": a.kind,
            }
        return data

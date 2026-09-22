from datetime import datetime
from typing import List, Optional

class Message:
    TYPE_TEXT = "TEXT"
    TYPE_FILE = "FILE"

    def __init__(
        self,
        room_id: int,
        user_id: int,
        content: str = "",
        id: Optional[int] = None,
        message_type: str = TYPE_TEXT,
        attachment_id: Optional[int] = None,
        created_at: Optional[datetime] = None,
        edited_at: Optional[datetime] = None,
        is_deleted: bool = False,
        sender_name: Optional[str] = None,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
        attachment: Optional["Attachment"] = None,
        reactions: Optional[List["Reaction"]] = None,
        reply_to_id: Optional[int] = None,
        forwarded_from_id: Optional[int] = None,
        pinned: bool = False,
        pinned_at: Optional[datetime] = None,
        pinned_by: Optional[int] = None,
        deleted_at: Optional[datetime] = None,
    ):
        # Tin nhắn dạng TEXT bắt buộc có nội dung; dạng FILE thì content là chú thích tùy chọn
        if message_type == self.TYPE_TEXT and (not content or len(content.strip()) == 0):
            raise ValueError("Nội dung tin nhắn không được để trống")
        if message_type == self.TYPE_FILE and attachment_id is None and attachment is None:
            raise ValueError("Tin nhắn dạng file phải có tệp đính kèm")

        self.id = id
        self.room_id = room_id
        self.user_id = user_id
        self.content = content or ""
        self.message_type = message_type
        self.attachment_id = attachment_id
        self.created_at = created_at or datetime.utcnow()
        self.edited_at = edited_at
        self.is_deleted = is_deleted
        self.reply_to_id = reply_to_id
        self.forwarded_from_id = forwarded_from_id
        self.pinned = pinned
        self.pinned_at = pinned_at
        self.pinned_by = pinned_by
        self.deleted_at = deleted_at

        # Dữ liệu bổ trợ cho tầng hiển thị
        self.sender_name = sender_name
        self.username = username
        self.avatar_url = avatar_url
        self.attachment = attachment
        self.reactions = reactions or []

    def is_sent_by(self, user_id: int) -> bool:
        return self.user_id == user_id

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.content = ""

    def edit(self, new_content: str) -> None:
        if not new_content or len(new_content.strip()) == 0:
            raise ValueError("Nội dung tin nhắn không được để trống")
        self.content = new_content.strip()
        self.edited_at = datetime.utcnow()


class Attachment:
    """Tệp đính kèm: ảnh, video, tài liệu."""

    KIND_IMAGE = "IMAGE"
    KIND_VIDEO = "VIDEO"
    KIND_AUDIO = "AUDIO"
    KIND_FILE = "FILE"

    MAX_SIZE_BYTES = 25 * 1024 * 1024  # 25MB

    def __init__(
        self,
        filename: str,
        stored_name: str,
        content_type: str,
        size_bytes: int,
        uploaded_by: int,
        id: Optional[int] = None,
        created_at: Optional[datetime] = None,
    ):
        if not filename or not filename.strip():
            raise ValueError("Tên tệp không được để trống")
        if size_bytes <= 0:
            raise ValueError("Tệp rỗng, không thể tải lên")
        if size_bytes > self.MAX_SIZE_BYTES:
            raise ValueError("Tệp vượt quá dung lượng cho phép (25MB)")

        self.id = id
        self.filename = filename.strip()
        self.stored_name = stored_name
        self.content_type = content_type or "application/octet-stream"
        self.size_bytes = size_bytes
        self.uploaded_by = uploaded_by
        self.created_at = created_at or datetime.utcnow()

    @property
    def kind(self) -> str:
        """Phân loại tệp dựa trên MIME type để frontend biết cách hiển thị."""
        ct = self.content_type.lower()
        if ct.startswith("image/"):
            return self.KIND_IMAGE
        if ct.startswith("video/"):
            return self.KIND_VIDEO
        if ct.startswith("audio/"):
            return self.KIND_AUDIO
        return self.KIND_FILE


class Reaction:
    """Biểu cảm của một người dùng trên một tin nhắn."""

    ALLOWED_EMOJIS = ("👍", "❤️", "😂", "😮", "😢", "🎉")

    def __init__(
        self,
        message_id: int,
        user_id: int,
        emoji: str,
        id: Optional[int] = None,
        created_at: Optional[datetime] = None,
    ):
        if emoji not in self.ALLOWED_EMOJIS:
            raise ValueError(f"Biểu cảm không được hỗ trợ: {emoji}")
        self.id = id
        self.message_id = message_id
        self.user_id = user_id
        self.emoji = emoji
        self.created_at = created_at or datetime.utcnow()

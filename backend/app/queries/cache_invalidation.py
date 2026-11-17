from typing import Any, Dict

from app.domain.interfaces import ICache, IEventPublisher
from app.queries.room_queries import ROOM_SUMMARY_PREFIX, room_summary_key, user_rooms_key

# Sự kiện làm đổi phần tóm tắt của phòng (tên, ảnh, số thành viên, tin cuối)
ROOM_SUMMARY_EVENTS = {
    "message.created",
    "message.updated",
    "message.deleted",
    "room.updated",
    "room.deleted",
    "room.avatar_updated",
    "room.member_joined",
    "room.member_left",
    "room.nickname_updated",   # biệt danh hiện làm tên người gửi tin cuối
}

# Sự kiện làm đổi danh sách phòng hoặc vai trò của MỘT người (payload có user_id)
USER_ROOMS_EVENTS = {
    "room.created",
    "room.member_joined",
    "room.member_left",
    "room.role_changed",
}


class RoomCacheInvalidator(IEventPublisher):
    """Giữ cache đường đọc đúng với đường ghi (Decorator quanh bộ phát sự kiện).

    Mọi thao tác ghi đều đã phát sự kiện realtime cho client. Lớp này nghe chính
    các sự kiện đó, xóa key liên quan rồi chuyển tiếp nguyên vẹn cho bộ phát bên
    trong. Nhờ vậy Service không cần biết có cache.

    Xóa chạy ngay trong luồng đang xử lý request, sau khi DB đã commit và trước khi
    trả phản hồi: người vừa ghi tải lại là thấy dữ liệu mới của chính mình.
    """

    def __init__(self, inner: IEventPublisher, cache: ICache):
        self.inner = inner
        self.cache = cache

    def publish_to_room(self, room_id: int, event: str, payload: Dict[str, Any]) -> None:
        if event in ROOM_SUMMARY_EVENTS:
            self.cache.delete(room_summary_key(room_id))
        self._invalidate_user(event, payload)
        self.inner.publish_to_room(room_id, event, payload)

    def publish_to_user(self, user_id: int, event: str, payload: Dict[str, Any]) -> None:
        self._invalidate_user(event, payload)
        self.inner.publish_to_user(user_id, event, payload)

    def publish_to_user_rooms(self, user_id: int, event: str, payload: Dict[str, Any]) -> None:
        if event == "user.updated":
            # Đổi họ tên làm đổi tên người gửi tin cuối ở mọi phòng người này tham gia.
            # Ở đây không biết đó là những phòng nào, mà việc đổi tên rất hiếm: xóa hết.
            self.cache.delete_prefix(ROOM_SUMMARY_PREFIX)
        self.inner.publish_to_user_rooms(user_id, event, payload)

    def revoke_room_access(self, user_id: int, room_id: int) -> None:
        self.cache.delete(user_rooms_key(user_id))
        self.inner.revoke_room_access(user_id, room_id)

    def _invalidate_user(self, event: str, payload: Dict[str, Any]) -> None:
        if event in USER_ROOMS_EVENTS and payload.get("user_id") is not None:
            self.cache.delete(user_rooms_key(int(payload["user_id"])))

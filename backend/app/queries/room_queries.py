"""Đường ĐỌC của danh sách phòng (CQRS mức nhẹ).

Đường ghi vẫn đi Router -> RoomService -> Domain -> Repository. Đường đọc này trả
thẳng dữ liệu đã ghép sẵn cho màn hình danh sách phòng, không đi qua thực thể domain,
nên tối ưu và cache được mà không đụng tới quy tắc nghiệp vụ.

Danh sách phòng ghép từ hai phần có vòng đời khác nhau:

    user:{id}:rooms      [(room_id, vai trò)]      đổi khi người này vào/rời phòng, đổi vai trò
    room:{id}:summary    thông tin phòng + số thành viên + tin cuối
                         đổi khi có tin mới, đổi tên phòng, thêm/bớt thành viên

Tách như vậy để một tin nhắn mới chỉ xóa đúng một key của phòng đó, thay vì xóa
danh sách của cả 50 thành viên.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple

from app.domain.interfaces import ICache, IRoomRepository


def user_rooms_key(user_id: int) -> str:
    return f"user:{user_id}:rooms"


def room_summary_key(room_id: int) -> str:
    return f"room:{room_id}:summary"


ROOM_SUMMARY_PREFIX = "room:"


class IRoomQueries(ABC):
    @abstractmethod
    def list_rooms(self, user_id: int, limit: int = 50, offset: int = 0) -> List[dict]:
        """Phòng người này tham gia, mỗi phòng một dict đúng khuôn RoomResponse."""
        pass


def _compose(memberships: List[Tuple[int, str]], summaries: Dict[int, dict]) -> List[dict]:
    # Phòng vừa bị xóa có thể còn trong danh sách thành viên đã cache: bỏ qua.
    # Tạo dict mới để nơi gọi không sửa được bản nằm trong cache.
    return [
        {**summaries[room_id], "my_role": role}
        for room_id, role in memberships
        if room_id in summaries
    ]


class RoomQueries(IRoomQueries):
    """Đọc thẳng DB: 4 truy vấn cố định cho cả danh sách."""

    def __init__(self, room_repo: IRoomRepository):
        self.room_repo = room_repo

    def memberships(self, user_id: int) -> List[Tuple[int, str]]:
        return self.room_repo.list_memberships(user_id)

    def room_summaries(self, room_ids: List[int]) -> Dict[int, dict]:
        return self.room_repo.get_room_summaries(room_ids)

    def list_rooms(self, user_id: int, limit: int = 50, offset: int = 0) -> List[dict]:
        page = self.memberships(user_id)[offset:offset + limit]
        return _compose(page, self.room_summaries([room_id for room_id, _ in page]))


class CachedRoomQueries(IRoomQueries):
    """Cache-Aside, bọc ngoài RoomQueries (Decorator, cùng interface).

    Đọc: có trong cache thì dùng; thiếu thì hỏi lớp bên trong rồi lưu lại.
    Không tự xóa cache: việc đó do RoomCacheInvalidator làm khi đường ghi phát sự kiện.
    TTL là lưới an toàn nếu có thay đổi nào chưa phát sự kiện.
    """

    def __init__(self, inner: RoomQueries, cache: ICache, ttl_seconds: int):
        self.inner = inner
        self.cache = cache
        self.ttl = ttl_seconds

    def list_rooms(self, user_id: int, limit: int = 50, offset: int = 0) -> List[dict]:
        key = user_rooms_key(user_id)
        memberships = self.cache.get(key)
        full_hit = memberships is not None
        if memberships is None:
            memberships = self.inner.memberships(user_id)
            self.cache.set(key, memberships, self.ttl)
        page = memberships[offset:offset + limit]

        room_ids = [room_id for room_id, _ in page]
        cached = self.cache.get_many(room_summary_key(rid) for rid in room_ids)
        summaries = {rid: cached[room_summary_key(rid)] for rid in room_ids if room_summary_key(rid) in cached}

        missing = [rid for rid in room_ids if rid not in summaries]
        self.cache.record_request(full_hit and not missing)
        if missing:
            # Các phòng còn thiếu lấy chung một lần, vẫn là truy vấn gộp của cải tiến N+1
            fresh = self.inner.room_summaries(missing)
            for rid, summary in fresh.items():
                self.cache.set(room_summary_key(rid), summary, self.ttl)
            summaries.update(fresh)
        return _compose(page, summaries)

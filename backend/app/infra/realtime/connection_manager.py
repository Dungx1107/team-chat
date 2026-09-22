import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Optional, Set

from starlette.websockets import WebSocket

from app.domain.interfaces import IEventPublisher

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


class ConnectionManager(IEventPublisher):
    """Quản lý các kết nối WebSocket đang mở và phát sự kiện tới đúng người nhận.

    Đây là bản cài đặt WebSocket của cổng IEventPublisher. Toàn bộ trạng thái
    kết nối nằm trong bộ nhớ tiến trình -- đủ dùng cho một instance.
    Ở Pha 2, khi chạy nhiều instance, lớp này sẽ được thay bằng bản dùng
    Redis Pub/Sub mà tầng nghiệp vụ không phải sửa gì.
    """

    def __init__(self) -> None:
        # user_id -> các socket của người đó (một người có thể mở nhiều tab)
        self._user_sockets: Dict[int, Set[WebSocket]] = defaultdict(set)
        # room_id -> các user_id đang theo dõi phòng
        self._room_users: Dict[int, Set[int]] = defaultdict(set)
        # socket -> user_id, để dọn dẹp khi ngắt kết nối
        self._socket_user: Dict[WebSocket, int] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = asyncio.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Ghi nhớ event loop chính, để code đồng bộ có thể đẩy việc vào."""
        self._loop = loop

    # ---------- Vòng đời kết nối ----------

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        await websocket.accept()
        async with self._lock:
            self._user_sockets[user_id].add(websocket)
            self._socket_user[websocket] = user_id

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            user_id = self._socket_user.pop(websocket, None)
            if user_id is None:
                return
            self._user_sockets[user_id].discard(websocket)
            if not self._user_sockets[user_id]:
                del self._user_sockets[user_id]
                # Người này không còn kết nối nào -> rời mọi phòng đang theo dõi
                for members in self._room_users.values():
                    members.discard(user_id)

    async def subscribe(self, user_id: int, room_id: int) -> None:
        async with self._lock:
            self._room_users[room_id].add(user_id)

    async def unsubscribe(self, user_id: int, room_id: int) -> None:
        async with self._lock:
            self._room_users[room_id].discard(user_id)

    def is_online(self, user_id: int) -> bool:
        return user_id in self._user_sockets

    def online_user_ids(self) -> Set[int]:
        return set(self._user_sockets.keys())

    # ---------- Gửi dữ liệu ----------

    async def _send_to_user(self, user_id: int, message: str) -> None:
        dead = []
        for ws in list(self._user_sockets.get(user_id, ())):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    async def _broadcast_room(self, room_id: int, message: str, exclude_user: Optional[int] = None) -> None:
        for uid in list(self._room_users.get(room_id, ())):
            if exclude_user is not None and uid == exclude_user:
                continue
            await self._send_to_user(uid, message)

    async def broadcast_room_async(self, room_id: int, event: str, payload: Dict[str, Any]) -> None:
        message = json.dumps({"event": event, "data": payload}, default=_json_default, ensure_ascii=False)
        await self._broadcast_room(room_id, message)

    # ---------- Cài đặt IEventPublisher (gọi được từ code đồng bộ) ----------

    def _dispatch(self, coro) -> None:
        """Đẩy một coroutine vào event loop chính.

        Endpoint đồng bộ của FastAPI chạy trong threadpool, không có event loop,
        nên phải dùng run_coroutine_threadsafe để bắc cầu sang loop chính.
        """
        if self._loop is None or self._loop.is_closed():
            logger.warning("Chưa gắn event loop, bỏ qua sự kiện realtime")
            return
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception as exc:
            logger.warning("Không phát được sự kiện realtime: %s", exc)

    def publish_to_room(self, room_id: int, event: str, payload: Dict[str, Any]) -> None:
        message = json.dumps({"event": event, "data": payload}, default=_json_default, ensure_ascii=False)
        self._dispatch(self._broadcast_room(room_id, message))

    def publish_to_user(self, user_id: int, event: str, payload: Dict[str, Any]) -> None:
        message = json.dumps({"event": event, "data": payload}, default=_json_default, ensure_ascii=False)
        self._dispatch(self._send_to_user(user_id, message))


# Một instance dùng chung cho toàn ứng dụng
connection_manager = ConnectionManager()

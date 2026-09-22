import json
import logging
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from app.infra.db.session import SessionLocal
from app.infra.realtime.connection_manager import connection_manager
from app.infra.security.jwt import decode_access_token
from app.repositories.room_repo import RoomRepository
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Realtime"])


def _can_access_room(user_id: int, room_id: int) -> bool:
    """Chỉ cho theo dõi phòng công khai, hoặc phòng riêng tư mà mình là thành viên."""
    db = SessionLocal()
    try:
        repo = RoomRepository(db)
        room = repo.get_by_id(room_id)
        if not room:
            return False
        if not room.is_private:
            return True
        return repo.get_member(room_id, user_id) is not None
    finally:
        db.close()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """Kênh realtime.

    Trình duyệt không gửi được header Authorization khi mở WebSocket,
    nên token truyền qua query string. Kết nối bị từ chối ngay nếu token sai.
    """
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        await websocket.close(code=4001, reason="Token không hợp lệ")
        return

    user_id = int(payload["sub"])
    await connection_manager.connect(websocket, user_id)

    try:
        await websocket.send_text(json.dumps({
            "event": "connected",
            "data": {"user_id": user_id},
        }, ensure_ascii=False))

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = msg.get("action")
            room_id = msg.get("room_id")

            if action == "subscribe" and room_id is not None:
                if _can_access_room(user_id, int(room_id)):
                    await connection_manager.subscribe(user_id, int(room_id))
                    await websocket.send_text(json.dumps({
                        "event": "subscribed",
                        "data": {"room_id": int(room_id)},
                    }, ensure_ascii=False))
                else:
                    await websocket.send_text(json.dumps({
                        "event": "error",
                        "data": {"detail": "Không có quyền theo dõi phòng này"},
                    }, ensure_ascii=False))

            elif action == "unsubscribe" and room_id is not None:
                await connection_manager.unsubscribe(user_id, int(room_id))

            elif action in ("typing.start", "typing.stop") and room_id is not None:
                if not _can_access_room(user_id, int(room_id)):
                    continue
                is_typing = action == "typing.start"
                await connection_manager.update_typing(user_id, int(room_id), is_typing)
                typing_user = None
                if is_typing:
                    db = SessionLocal()
                    try:
                        user = UserRepository(db).get_by_id(user_id)
                        if user:
                            typing_user = {
                                "id": user.id,
                                "full_name": user.full_name,
                                "avatar_url": user.avatar_url,
                            }
                    finally:
                        db.close()
                payload = {"room_id": int(room_id), "user_id": user_id}
                if typing_user:
                    payload["user"] = typing_user
                await connection_manager.broadcast_room_async(
                    int(room_id),
                    action,
                    payload,
                    exclude_user=user_id,
                )

            elif action == "ping":
                await websocket.send_text(json.dumps({"event": "pong", "data": {}}))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Lỗi kết nối WebSocket của user %s: %s", user_id, exc)
    finally:
        await connection_manager.disconnect(websocket)

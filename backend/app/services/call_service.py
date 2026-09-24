import json
from typing import Any, Dict, List, Optional
from app.domain.interfaces import (
    ICallRepository,
    IRoomRepository,
    IUserRepository,
    IEventPublisher,
)
from app.domain.interfaces.event_publisher import NullEventPublisher
from app.domain.models import Call, CallParticipant


class CallService:
    """Nghiệp vụ cuộc gọi thoại/video.

    Âm thanh và hình ảnh đi thẳng giữa hai trình duyệt qua WebRTC, không qua
    server. Server chỉ làm hai việc:
      1. Quản lý vòng đời cuộc gọi (mời, nhận, từ chối, kết thúc) và lưu lịch sử.
      2. Chuyển tiếp tín hiệu kết nối WebRTC (SDP offer/answer, ICE candidate)
         giữa những người đang ở trong cùng một cuộc gọi -- gọi là signaling.

    Như mọi service khác, lớp này không biết WebSocket là gì: mọi sự kiện đi
    qua IEventPublisher.
    """

    SIGNAL_TYPES = ("offer", "answer", "ice")
    MAX_SIGNAL_BYTES = 64 * 1024

    def __init__(
        self,
        call_repo: ICallRepository,
        room_repo: IRoomRepository,
        user_repo: IUserRepository,
        event_publisher: Optional[IEventPublisher] = None,
    ):
        self.call_repo = call_repo
        self.room_repo = room_repo
        self.user_repo = user_repo
        self.events = event_publisher or NullEventPublisher()

    # ---------- Tiện ích ----------

    def _get_call_or_fail(self, call_id: int) -> Call:
        call = self.call_repo.get_by_id(call_id)
        if not call:
            raise ValueError("Cuộc gọi không tồn tại")
        return call

    def _user_brief(self, user_id: int) -> Dict[str, Any]:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            return {"id": user_id, "full_name": f"Người dùng #{user_id}", "username": None, "avatar_url": None}
        return {
            "id": user.id,
            "full_name": user.full_name,
            "username": user.username,
            "avatar_url": user.avatar_url,
        }

    def to_payload(self, call: Call) -> Dict[str, Any]:
        return {
            "id": call.id,
            "room_id": call.room_id,
            "kind": call.kind,
            "mode": call.mode,
            "status": call.status,
            "initiator_id": call.initiator_id,
            "created_at": call.created_at,
            "answered_at": call.answered_at,
            "ended_at": call.ended_at,
            "duration_seconds": call.duration_seconds,
            "participants": [
                {**self._user_brief(p.user_id), "state": p.state}
                for p in call.participants
            ],
            "active_participant_ids": call.active_participant_ids(),
        }

    def _notify(self, call: Call, event: str, exclude: Optional[int] = None) -> None:
        payload = self.to_payload(call)
        for uid in call.participant_ids():
            if uid != exclude:
                self.events.publish_to_user(uid, event, payload)

    # ---------- Vòng đời cuộc gọi ----------

    def start_call(self, caller_id: int, callee_id: int, room_id: int, kind: str) -> Call:
        if caller_id == callee_id:
            raise ValueError("Không thể tự gọi cho chính mình")

        if not self.room_repo.get_by_id(room_id):
            raise ValueError("Phòng chat không tồn tại")

        # Chỉ gọi được cho người ở cùng phòng -- tránh việc gọi bừa cho bất kỳ ai
        if not self.room_repo.get_member(room_id, caller_id):
            raise PermissionError("Bạn không phải thành viên của phòng này")
        if not self.room_repo.get_member(room_id, callee_id):
            raise PermissionError("Người nhận không ở trong phòng này")

        if not self.user_repo.get_by_id(callee_id):
            raise ValueError("Người nhận không tồn tại")

        # Mỗi người chỉ ở trong tối đa một cuộc gọi tại một thời điểm
        if self.call_repo.find_open_call_of_user(caller_id):
            raise RuntimeError("Bạn đang ở trong một cuộc gọi khác")
        if self.call_repo.find_open_call_of_user(callee_id):
            raise RuntimeError("Người nhận đang bận trong cuộc gọi khác")

        call = Call(
            initiator_id=caller_id,
            kind=kind,
            room_id=room_id,
            participants=[
                CallParticipant(call_id=None, user_id=caller_id, state=CallParticipant.STATE_JOINED),
                CallParticipant(call_id=None, user_id=callee_id, state=CallParticipant.STATE_INVITED),
            ],
        )
        created = self.call_repo.create(call)

        self.events.publish_to_user(callee_id, "call.incoming", self.to_payload(created))
        return created

    # ---------- Gọi nhóm ----------

    def start_group_call(self, user_id: int, room_id: int, kind: str) -> Call:
        """Mở cuộc gọi nhóm trong phòng.

        Khác gọi 1-1: không đổ chuông cho ai cả. Cuộc gọi vào trạng thái ACTIVE
        ngay, những người trong phòng thấy thông báo và tự quyết định có vào hay không.
        """
        if not self.room_repo.get_by_id(room_id):
            raise ValueError("Phòng chat không tồn tại")
        if not self.room_repo.get_member(room_id, user_id):
            raise PermissionError("Bạn không phải thành viên của phòng này")

        # Phòng đã có cuộc gọi nhóm thì vào luôn cái đó, không mở cái thứ hai
        existing = self.call_repo.find_active_group_call(room_id)
        if existing:
            return self.join_call(existing.id, user_id)

        if self.call_repo.find_open_call_of_user(user_id):
            raise RuntimeError("Bạn đang ở trong một cuộc gọi khác")

        call = Call(
            initiator_id=user_id,
            kind=kind,
            mode=Call.MODE_GROUP,
            room_id=room_id,
            status=Call.STATUS_ACTIVE,
            participants=[
                CallParticipant(call_id=None, user_id=user_id, state=CallParticipant.STATE_JOINED)
            ],
        )
        created = self.call_repo.create(call)

        # Báo cho cả phòng biết có cuộc gọi để hiện nút "Tham gia"
        self.events.publish_to_room(room_id, "call.room_started", self.to_payload(created))
        return created

    def join_call(self, call_id: int, user_id: int) -> Call:
        call = self._get_call_or_fail(call_id)
        if call.room_id and not self.room_repo.get_member(call.room_id, user_id):
            raise PermissionError("Bạn không phải thành viên của phòng này")

        # Đang bận ở cuộc gọi khác thì không vào được
        other = self.call_repo.find_open_call_of_user(user_id)
        if other and other.id != call.id:
            raise RuntimeError("Bạn đang ở trong một cuộc gọi khác")

        already_in = user_id in call.active_participant_ids()
        call.join(user_id)  # entity kiểm tra kiểu cuộc gọi, trạng thái và sức chứa
        saved = self.call_repo.save(call)

        if not already_in:
            # Những người đang ở trong sẽ chủ động gọi tới người mới
            payload = {
                "call_id": saved.id,
                "user": self._user_brief(user_id),
                "call": self.to_payload(saved),
            }
            for uid in saved.active_participant_ids():
                if uid != user_id:
                    self.events.publish_to_user(uid, "call.participant_joined", payload)
            if saved.room_id:
                self.events.publish_to_room(saved.room_id, "call.room_updated", self.to_payload(saved))
        return saved

    def leave_call(self, call_id: int, user_id: int) -> Call:
        call = self._get_call_or_fail(call_id)
        if not call.has_participant(user_id):
            raise PermissionError("Bạn không nằm trong cuộc gọi này")

        left = call.leave(user_id)
        saved = self.call_repo.save(call)
        if not left:
            return saved

        payload = {"call_id": saved.id, "user_id": user_id, "call": self.to_payload(saved)}
        for uid in saved.active_participant_ids():
            self.events.publish_to_user(uid, "call.participant_left", payload)
        if saved.room_id:
            event = "call.room_ended" if not saved.is_open() else "call.room_updated"
            self.events.publish_to_room(saved.room_id, event, self.to_payload(saved))
        return saved

    def get_active_group_call(self, room_id: int, user_id: int) -> Optional[Call]:
        if not self.room_repo.get_member(room_id, user_id):
            raise PermissionError("Bạn không phải thành viên của phòng này")
        return self.call_repo.find_active_group_call(room_id)

    # ---------- Gọi 1-1 ----------

    def accept_call(self, call_id: int, user_id: int) -> Call:
        call = self._get_call_or_fail(call_id)
        call.accept(user_id)  # entity tự kiểm tra trạng thái và quyền
        saved = self.call_repo.save(call)
        # Báo cho mọi người, kể cả các tab khác của chính người vừa nhận
        # để chúng tắt chuông
        self._notify(saved, "call.accepted")
        return saved

    def decline_call(self, call_id: int, user_id: int) -> Call:
        call = self._get_call_or_fail(call_id)
        call.decline(user_id)
        saved = self.call_repo.save(call)
        self._notify(saved, "call.ended")
        return saved

    def end_call(self, call_id: int, user_id: int, missed: bool = False) -> Call:
        call = self._get_call_or_fail(call_id)
        if not call.is_open():
            return call
        call.end(user_id, missed=missed)
        saved = self.call_repo.save(call)
        self._notify(saved, "call.ended")
        return saved

    def end_calls_of_user(self, user_id: int) -> None:
        """Dọn cuộc gọi dở dang khi một người mất hết kết nối (đóng tab, rớt mạng).

        Gọi nhóm chỉ rời một mình; những người còn lại vẫn nói chuyện tiếp.
        """
        call = self.call_repo.find_open_call_of_user(user_id)
        if not call:
            return
        if call.is_group():
            self.leave_call(call.id, user_id)
        else:
            self.end_call(call.id, user_id, missed=call.status == Call.STATUS_RINGING)

    def get_call(self, call_id: int, user_id: int) -> Call:
        call = self._get_call_or_fail(call_id)
        if not call.has_participant(user_id):
            raise PermissionError("Bạn không nằm trong cuộc gọi này")
        return call

    def list_history(self, user_id: int, limit: int = 30) -> List[Call]:
        return self.call_repo.list_by_user(user_id, limit=limit)

    # ---------- Signaling ----------

    def relay_signal(
        self, call_id: int, from_user_id: int, to_user_id: int, signal: Dict[str, Any]
    ) -> None:
        """Chuyển tiếp tín hiệu WebRTC sang người bên kia.

        Chỉ chuyển giữa hai người cùng nằm trong một cuộc gọi đang mở -- nếu
        không, WebSocket sẽ thành một kênh cho phép ai cũng nhắn thẳng tới ai.
        """
        if not isinstance(signal, dict) or signal.get("type") not in self.SIGNAL_TYPES:
            raise ValueError("Tín hiệu không hợp lệ")
        if len(json.dumps(signal)) > self.MAX_SIGNAL_BYTES:
            raise ValueError("Tín hiệu quá lớn")

        call = self._get_call_or_fail(call_id)
        if not call.is_open():
            raise ValueError("Cuộc gọi đã kết thúc")
        if not call.has_participant(from_user_id) or not call.has_participant(to_user_id):
            raise PermissionError("Chỉ người trong cuộc gọi mới gửi được tín hiệu")
        if from_user_id == to_user_id:
            raise ValueError("Không thể gửi tín hiệu cho chính mình")

        self.events.publish_to_user(to_user_id, "call.signal", {
            "call_id": call_id,
            "from_user_id": from_user_id,
            "signal": signal,
        })

from datetime import datetime
from typing import List, Optional


class CallParticipant:
    """Một người trong cuộc gọi.

    Cuộc gọi được mô hình hóa bằng danh sách người tham gia thay vì cặp
    (người gọi, người nghe). Gọi 1-1 chỉ là trường hợp có đúng hai người;
    khi mở rộng sang gọi theo phòng sẽ không phải đổi cấu trúc dữ liệu.
    """

    STATE_INVITED = "INVITED"
    STATE_JOINED = "JOINED"
    STATE_DECLINED = "DECLINED"
    STATE_LEFT = "LEFT"

    def __init__(
        self,
        call_id: Optional[int],
        user_id: int,
        state: str = STATE_INVITED,
        id: Optional[int] = None,
        joined_at: Optional[datetime] = None,
        left_at: Optional[datetime] = None,
    ):
        self.id = id
        self.call_id = call_id
        self.user_id = user_id
        self.state = state
        self.joined_at = joined_at
        self.left_at = left_at

    def is_active(self) -> bool:
        return self.state in (self.STATE_INVITED, self.STATE_JOINED)


class Call:
    """Cuộc gọi thoại/video.

    Vòng đời:  RINGING -> ACTIVE -> ENDED
               RINGING -> REJECTED | MISSED | CANCELED
    Luật chuyển trạng thái nằm trong entity để service không phải tự kiểm tra.
    """

    KIND_AUDIO = "AUDIO"
    KIND_VIDEO = "VIDEO"
    VALID_KINDS = (KIND_AUDIO, KIND_VIDEO)

    STATUS_RINGING = "RINGING"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_ENDED = "ENDED"
    STATUS_REJECTED = "REJECTED"
    STATUS_MISSED = "MISSED"
    STATUS_CANCELED = "CANCELED"

    OPEN_STATUSES = (STATUS_RINGING, STATUS_ACTIVE)

    def __init__(
        self,
        initiator_id: int,
        kind: str = KIND_VIDEO,
        room_id: Optional[int] = None,
        status: str = STATUS_RINGING,
        id: Optional[int] = None,
        created_at: Optional[datetime] = None,
        answered_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        participants: Optional[List[CallParticipant]] = None,
    ):
        if kind not in self.VALID_KINDS:
            raise ValueError(f"Loại cuộc gọi không hợp lệ: {kind}")
        self.id = id
        self.room_id = room_id
        self.initiator_id = initiator_id
        self.kind = kind
        self.status = status
        self.created_at = created_at or datetime.utcnow()
        self.answered_at = answered_at
        self.ended_at = ended_at
        self.participants: List[CallParticipant] = participants or []

    # ---------- Truy vấn ----------

    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    def participant_ids(self) -> List[int]:
        return [p.user_id for p in self.participants]

    def has_participant(self, user_id: int) -> bool:
        return user_id in self.participant_ids()

    def get_participant(self, user_id: int) -> Optional[CallParticipant]:
        for p in self.participants:
            if p.user_id == user_id:
                return p
        return None

    def other_participant_ids(self, user_id: int) -> List[int]:
        return [uid for uid in self.participant_ids() if uid != user_id]

    @property
    def duration_seconds(self) -> Optional[int]:
        if not self.answered_at or not self.ended_at:
            return None
        return max(0, int((self.ended_at - self.answered_at).total_seconds()))

    # ---------- Chuyển trạng thái ----------

    def accept(self, user_id: int) -> None:
        if self.status != self.STATUS_RINGING:
            raise ValueError("Cuộc gọi không còn đổ chuông")
        if user_id == self.initiator_id:
            raise ValueError("Người gọi không thể tự nhận cuộc gọi của mình")
        participant = self.get_participant(user_id)
        if not participant:
            raise PermissionError("Bạn không nằm trong cuộc gọi này")
        now = datetime.utcnow()
        participant.state = CallParticipant.STATE_JOINED
        participant.joined_at = now
        self.status = self.STATUS_ACTIVE
        self.answered_at = now

    def decline(self, user_id: int) -> None:
        if self.status != self.STATUS_RINGING:
            raise ValueError("Cuộc gọi không còn đổ chuông")
        participant = self.get_participant(user_id)
        if not participant or user_id == self.initiator_id:
            raise PermissionError("Bạn không thể từ chối cuộc gọi này")
        participant.state = CallParticipant.STATE_DECLINED
        participant.left_at = datetime.utcnow()
        self._close(self.STATUS_REJECTED)

    def end(self, user_id: int, missed: bool = False) -> None:
        """Kết thúc cuộc gọi.

        Đang đổ chuông mà người gọi dập máy -> CANCELED (hoặc MISSED nếu hết giờ chờ).
        Đang nói chuyện mà một bên dập máy -> ENDED.
        """
        if not self.is_open():
            return
        if not self.has_participant(user_id):
            raise PermissionError("Bạn không nằm trong cuộc gọi này")

        if self.status == self.STATUS_RINGING:
            final = self.STATUS_MISSED if missed else self.STATUS_CANCELED
        else:
            final = self.STATUS_ENDED
        self._close(final)

    def _close(self, final_status: str) -> None:
        now = datetime.utcnow()
        self.status = final_status
        self.ended_at = now
        for p in self.participants:
            if p.is_active():
                p.state = CallParticipant.STATE_LEFT
                p.left_at = p.left_at or now

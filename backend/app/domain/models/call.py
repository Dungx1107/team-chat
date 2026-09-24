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

    MODE_DIRECT = "DIRECT"   # gọi 1-1, có đổ chuông
    MODE_GROUP = "GROUP"     # gọi nhóm trong phòng, ai muốn vào thì vào
    VALID_MODES = (MODE_DIRECT, MODE_GROUP)

    # Gọi nhóm hiện dùng mô hình mesh: mỗi người nối trực tiếp tới từng người
    # còn lại, nên số kết nối tăng theo bình phương. Giới hạn 6 người để máy
    # yếu vẫn chịu được; muốn đông hơn phải chuyển sang máy chủ media (SFU).
    MAX_GROUP_PARTICIPANTS = 6

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
        mode: str = MODE_DIRECT,
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
        if mode not in self.VALID_MODES:
            raise ValueError(f"Kiểu cuộc gọi không hợp lệ: {mode}")
        self.id = id
        self.mode = mode
        self.room_id = room_id
        self.initiator_id = initiator_id
        self.kind = kind
        self.status = status
        self.created_at = created_at or datetime.utcnow()
        # Cuộc gọi nhóm vào ACTIVE ngay khi mở, không có bước bấm nghe máy.
        # Không đặt mốc này thì thời lượng cuộc gọi nhóm luôn rỗng.
        if answered_at is None and status == self.STATUS_ACTIVE:
            answered_at = self.created_at
        self.answered_at = answered_at
        self.ended_at = ended_at
        self.participants: List[CallParticipant] = participants or []

    # ---------- Truy vấn ----------

    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    def is_group(self) -> bool:
        return self.mode == self.MODE_GROUP

    def active_participant_ids(self) -> List[int]:
        """Những người đang thực sự ở trong cuộc gọi (đã vào và chưa rời)."""
        return [p.user_id for p in self.participants if p.state == CallParticipant.STATE_JOINED]

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

    # ---------- Gọi nhóm ----------

    def join(self, user_id: int) -> CallParticipant:
        """Tham gia cuộc gọi nhóm đang diễn ra."""
        if not self.is_group():
            raise ValueError("Chỉ cuộc gọi nhóm mới tham gia được")
        if self.status != self.STATUS_ACTIVE:
            raise ValueError("Cuộc gọi đã kết thúc")

        participant = self.get_participant(user_id)
        if participant and participant.state == CallParticipant.STATE_JOINED:
            return participant  # đã ở trong rồi, gọi lại cũng không sao

        if len(self.active_participant_ids()) >= self.MAX_GROUP_PARTICIPANTS:
            raise RuntimeError(
                f"Cuộc gọi đã đủ {self.MAX_GROUP_PARTICIPANTS} người"
            )

        now = datetime.utcnow()
        if participant:
            # Người từng rời đi quay lại
            participant.state = CallParticipant.STATE_JOINED
            participant.joined_at = now
            participant.left_at = None
        else:
            participant = CallParticipant(
                call_id=self.id,
                user_id=user_id,
                state=CallParticipant.STATE_JOINED,
                joined_at=now,
            )
            self.participants.append(participant)
        return participant

    def leave(self, user_id: int) -> bool:
        """Rời cuộc gọi nhóm. Người cuối cùng rời đi thì cuộc gọi kết thúc."""
        participant = self.get_participant(user_id)
        if not participant or participant.state != CallParticipant.STATE_JOINED:
            return False

        participant.state = CallParticipant.STATE_LEFT
        participant.left_at = datetime.utcnow()

        if not self.active_participant_ids():
            self._close(self.STATUS_ENDED)
        return True

    # ---------- Gọi 1-1 ----------

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

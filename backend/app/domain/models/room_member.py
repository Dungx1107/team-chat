from datetime import datetime
from typing import Optional

class RoomMember:
    """Thành viên của một phòng, kèm vai trò quyết định quyền hạn.

    Phân cấp quyền: OWNER > ADMIN > MEMBER
    """

    ROLE_OWNER = "OWNER"
    ROLE_ADMIN = "ADMIN"
    ROLE_MEMBER = "MEMBER"

    VALID_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER)

    # Thứ bậc để so sánh quyền: số càng lớn quyền càng cao
    _RANK = {ROLE_MEMBER: 1, ROLE_ADMIN: 2, ROLE_OWNER: 3}

    def __init__(
        self,
        room_id: int,
        user_id: int,
        role: str = ROLE_MEMBER,
        id: Optional[int] = None,
        joined_at: Optional[datetime] = None
    ):
        if role not in self.VALID_ROLES:
            raise ValueError(f"Vai trò không hợp lệ: {role}")
        self.id = id
        self.room_id = room_id
        self.user_id = user_id
        self.role = role
        self.joined_at = joined_at or datetime.utcnow()

    @property
    def rank(self) -> int:
        return self._RANK[self.role]

    def is_owner(self) -> bool:
        return self.role == self.ROLE_OWNER

    def is_admin(self) -> bool:
        return self.role == self.ROLE_ADMIN

    def outranks(self, other: "RoomMember") -> bool:
        """Quyền của mình có cao hơn người kia không."""
        return self.rank > other.rank

    # --- Các quyền hạn cụ thể, đóng gói ngay trong entity ---

    def can_delete_room(self) -> bool:
        """Chỉ chủ phòng mới được xóa phòng."""
        return self.is_owner()

    def can_manage_members(self) -> bool:
        """Thêm/xóa thành viên: OWNER và ADMIN."""
        return self.rank >= self._RANK[self.ROLE_ADMIN]

    def can_manage_roles(self) -> bool:
        """Chỉ chủ phòng được phong/giáng vai trò."""
        return self.is_owner()

    def can_moderate_messages(self) -> bool:
        """Xóa tin nhắn của người khác: OWNER và ADMIN."""
        return self.rank >= self._RANK[self.ROLE_ADMIN]

    def can_update_room(self) -> bool:
        """Đổi tên/mô tả phòng: OWNER và ADMIN."""
        return self.rank >= self._RANK[self.ROLE_ADMIN]

    def can_send_message(self) -> bool:
        return True

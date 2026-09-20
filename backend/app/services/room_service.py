from typing import List, Optional, Tuple
from app.domain.interfaces import IRoomRepository, IUserRepository, IEventPublisher
from app.domain.interfaces.event_publisher import NullEventPublisher
from app.domain.models import Room, RoomMember, User


class RoomService:
    """Nghiệp vụ phòng chat và phân quyền.

    Lưu ý kiến trúc: lớp này không import fastapi, sqlalchemy hay websocket.
    Nó chỉ làm việc với các interface của tầng domain.
    """

    def __init__(
        self,
        room_repo: IRoomRepository,
        user_repo: Optional[IUserRepository] = None,
        event_publisher: Optional[IEventPublisher] = None,
    ):
        self.room_repo = room_repo
        self.user_repo = user_repo
        self.events = event_publisher or NullEventPublisher()

    # ---------- Kiểm tra quyền dùng chung ----------

    def _get_room_or_fail(self, room_id: int) -> Room:
        room = self.room_repo.get_by_id(room_id)
        if not room:
            raise ValueError("Phòng chat không tồn tại")
        return room

    def require_membership(self, room_id: int, user_id: int) -> RoomMember:
        """Người dùng phải là thành viên thì mới thao tác được trong phòng."""
        member = self.room_repo.get_member(room_id, user_id)
        if not member:
            raise PermissionError("Bạn không phải thành viên của phòng này")
        return member

    def can_view_room(self, room: Room, user_id: int) -> bool:
        if not room.is_private:
            return True
        return self.room_repo.get_member(room.id, user_id) is not None

    # ---------- Tạo và quản lý phòng ----------

    def create_room(
        self,
        name: str,
        owner_id: int,
        description: Optional[str] = None,
        is_private: bool = False,
    ) -> Room:
        new_room = Room(
            name=name,
            owner_id=owner_id,
            description=description,
            is_private=is_private,
        )
        created_room = self.room_repo.create(new_room)

        # Người tạo luôn là OWNER
        self.room_repo.add_member(
            RoomMember(
                room_id=created_room.id,
                user_id=owner_id,
                role=RoomMember.ROLE_OWNER,
            )
        )
        return created_room

    def list_rooms(self, user_id: int, limit: int = 50, offset: int = 0) -> List[Room]:
        """Trả về phòng công khai + phòng riêng tư mà người dùng có tham gia."""
        return self.room_repo.list_visible_to_user(user_id, limit=limit, offset=offset)

    def get_room(self, room_id: int, user_id: int) -> Room:
        room = self._get_room_or_fail(room_id)
        if not self.can_view_room(room, user_id):
            raise PermissionError("Đây là phòng riêng tư, bạn không có quyền xem")
        return room

    def update_room(
        self,
        room_id: int,
        user_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Room:
        room = self._get_room_or_fail(room_id)
        member = self.require_membership(room_id, user_id)
        if not member.can_update_room():
            raise PermissionError("Chỉ chủ phòng hoặc quản trị viên mới được sửa thông tin phòng")

        if name is not None:
            room.rename(name)
        if description is not None:
            room.description = description.strip() or None

        updated = self.room_repo.update(room)
        self.events.publish_to_room(room_id, "room.updated", {
            "id": updated.id,
            "name": updated.name,
            "description": updated.description,
            "is_private": updated.is_private,
        })
        return updated

    def delete_room(self, room_id: int, user_id: int) -> bool:
        room = self._get_room_or_fail(room_id)
        member = self.room_repo.get_member(room_id, user_id)

        # Chủ sở hữu ghi trong bảng rooms là nguồn sự thật cuối cùng
        is_owner = room.is_owner(user_id) or (member is not None and member.can_delete_room())
        if not is_owner:
            raise PermissionError("Bạn không có quyền xóa phòng này (chỉ chủ phòng mới được xóa)")

        self.events.publish_to_room(room_id, "room.deleted", {"id": room_id})
        return self.room_repo.delete(room_id)

    # ---------- Thành viên ----------

    def join_room(self, room_id: int, user_id: int) -> RoomMember:
        room = self._get_room_or_fail(room_id)

        if room.is_private:
            raise PermissionError("Phòng riêng tư, bạn cần được chủ phòng mời vào")

        existing = self.room_repo.get_member(room_id, user_id)
        if existing:
            return existing

        member = self.room_repo.add_member(
            RoomMember(room_id=room_id, user_id=user_id, role=RoomMember.ROLE_MEMBER)
        )
        self._publish_member_event(room_id, user_id, "room.member_joined")
        return member

    def leave_room(self, room_id: int, user_id: int) -> bool:
        room = self._get_room_or_fail(room_id)
        member = self.require_membership(room_id, user_id)

        if member.is_owner() or room.is_owner(user_id):
            raise PermissionError(
                "Chủ phòng không thể rời phòng. Hãy chuyển quyền cho người khác hoặc xóa phòng."
            )

        removed = self.room_repo.remove_member(room_id, user_id)
        if removed:
            self._publish_member_event(room_id, user_id, "room.member_left")
        return removed

    def add_member(self, room_id: int, actor_id: int, target_user_id: int) -> RoomMember:
        """Mời người khác vào phòng -- cách duy nhất để vào phòng riêng tư."""
        self._get_room_or_fail(room_id)
        actor = self.require_membership(room_id, actor_id)
        if not actor.can_manage_members():
            raise PermissionError("Chỉ chủ phòng hoặc quản trị viên mới được thêm thành viên")

        if self.user_repo and not self.user_repo.get_by_id(target_user_id):
            raise ValueError("Người dùng không tồn tại")

        existing = self.room_repo.get_member(room_id, target_user_id)
        if existing:
            return existing

        member = self.room_repo.add_member(
            RoomMember(room_id=room_id, user_id=target_user_id, role=RoomMember.ROLE_MEMBER)
        )
        self._publish_member_event(room_id, target_user_id, "room.member_joined")
        return member

    def remove_member(self, room_id: int, actor_id: int, target_user_id: int) -> bool:
        room = self._get_room_or_fail(room_id)
        actor = self.require_membership(room_id, actor_id)
        if not actor.can_manage_members():
            raise PermissionError("Chỉ chủ phòng hoặc quản trị viên mới được xóa thành viên")

        target = self.room_repo.get_member(room_id, target_user_id)
        if not target:
            raise ValueError("Người này không phải thành viên của phòng")

        if target.is_owner() or room.is_owner(target_user_id):
            raise PermissionError("Không thể xóa chủ phòng")

        # Quản trị viên không đụng được tới quản trị viên khác, chỉ chủ phòng mới có quyền đó
        if not actor.outranks(target) and actor_id != target_user_id:
            raise PermissionError("Bạn không có quyền xóa thành viên có vai trò ngang hoặc cao hơn")

        removed = self.room_repo.remove_member(room_id, target_user_id)
        if removed:
            self._publish_member_event(room_id, target_user_id, "room.member_left")
        return removed

    def change_member_role(
        self, room_id: int, actor_id: int, target_user_id: int, new_role: str
    ) -> RoomMember:
        room = self._get_room_or_fail(room_id)
        actor = self.require_membership(room_id, actor_id)
        if not actor.can_manage_roles():
            raise PermissionError("Chỉ chủ phòng mới được thay đổi vai trò thành viên")

        if new_role not in (RoomMember.ROLE_ADMIN, RoomMember.ROLE_MEMBER):
            raise ValueError("Chỉ có thể đặt vai trò ADMIN hoặc MEMBER")

        target = self.room_repo.get_member(room_id, target_user_id)
        if not target:
            raise ValueError("Người này không phải thành viên của phòng")

        if target.is_owner() or room.is_owner(target_user_id):
            raise PermissionError("Không thể đổi vai trò của chủ phòng")

        updated = self.room_repo.update_member_role(room_id, target_user_id, new_role)
        self.events.publish_to_room(room_id, "room.role_changed", {
            "room_id": room_id,
            "user_id": target_user_id,
            "role": new_role,
        })
        return updated

    def list_members(self, room_id: int, user_id: int) -> List[Tuple[RoomMember, User]]:
        room = self._get_room_or_fail(room_id)
        if not self.can_view_room(room, user_id):
            raise PermissionError("Đây là phòng riêng tư, bạn không có quyền xem")
        return self.room_repo.list_members(room_id)

    # ---------- Tiện ích nội bộ ----------

    def _publish_member_event(self, room_id: int, user_id: int, event: str) -> None:
        payload = {"room_id": room_id, "user_id": user_id}
        if self.user_repo:
            user = self.user_repo.get_by_id(user_id)
            if user:
                payload.update({
                    "username": user.username,
                    "full_name": user.full_name,
                    "avatar_url": user.avatar_url,
                })
        self.events.publish_to_room(room_id, event, payload)

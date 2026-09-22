from typing import List, Optional, Tuple
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.domain.interfaces import IRoomRepository
from app.domain.models import Room, RoomMember, User
from app.infra.db.models import RoomModel, RoomMemberModel, UserModel, MessageModel, AttachmentModel

class RoomRepository(IRoomRepository):
    def __init__(self, db: Session):
        self.db = db

    # ---------- Ánh xạ Model <-> Entity ----------

    def _to_room_entity(self, model: Optional[RoomModel]) -> Optional[Room]:
        if not model:
            return None
        return Room(
            id=model.id,
            name=model.name,
            description=model.description,
            is_private=model.is_private,
            owner_id=model.owner_id,
            avatar_url=model.avatar_url,
            created_at=model.created_at,
        )

    def _to_member_entity(self, model: Optional[RoomMemberModel]) -> Optional[RoomMember]:
        if not model:
            return None
        return RoomMember(
            id=model.id,
            room_id=model.room_id,
            user_id=model.user_id,
            role=model.role,
            joined_at=model.joined_at,
        )

    def _to_user_entity(self, model: UserModel) -> User:
        return User(
            id=model.id,
            email=model.email,
            username=model.username,
            password_hash=model.password_hash,
            first_name=model.first_name,
            last_name=model.last_name,
            is_active=model.is_active,
            avatar_url=model.avatar_url,
            bio=model.bio,
            status=model.status,
            created_at=model.created_at,
        )

    # ---------- Phòng ----------

    def create(self, room: Room) -> Room:
        model = RoomModel(
            name=room.name,
            description=room.description,
            is_private=room.is_private,
            owner_id=room.owner_id,
            avatar_url=room.avatar_url,
            created_at=room.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_room_entity(model)

    def get_by_id(self, room_id: int) -> Optional[Room]:
        model = self.db.query(RoomModel).filter(RoomModel.id == room_id).first()
        return self._to_room_entity(model)

    def update(self, room: Room) -> Room:
        model = self.db.query(RoomModel).filter(RoomModel.id == room.id).first()
        if not model:
            raise ValueError("Phòng chat không tồn tại")
        model.name = room.name
        model.description = room.description
        model.is_private = room.is_private
        model.avatar_url = room.avatar_url
        self.db.commit()
        self.db.refresh(model)
        return self._to_room_entity(model)

    def list_all(self, limit: int = 50, offset: int = 0) -> List[Room]:
        models = (
            self.db.query(RoomModel)
            .filter(RoomModel.is_private.is_(False))
            .order_by(RoomModel.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_room_entity(m) for m in models]

    def list_visible_to_user(self, user_id: int, limit: int = 50, offset: int = 0) -> List[Room]:
        """Phòng công khai, cộng thêm phòng riêng tư mà người này là thành viên.

        Dùng outer join thay vì subquery lồng để tránh N+1 khi số phòng lớn.
        """
        models = (
            self.db.query(RoomModel)
            .outerjoin(
                RoomMemberModel,
                (RoomMemberModel.room_id == RoomModel.id)
                & (RoomMemberModel.user_id == user_id),
            )
            .filter(
                or_(
                    RoomModel.is_private.is_(False),
                    RoomMemberModel.id.isnot(None),
                )
            )
            .order_by(RoomModel.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_room_entity(m) for m in models]

    def delete(self, room_id: int) -> bool:
        model = self.db.query(RoomModel).filter(RoomModel.id == room_id).first()
        if not model:
            return False
        self.db.delete(model)
        self.db.commit()
        return True

    # ---------- Thành viên ----------

    def add_member(self, member: RoomMember) -> RoomMember:
        model = RoomMemberModel(
            room_id=member.room_id,
            user_id=member.user_id,
            role=member.role,
            joined_at=member.joined_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_member_entity(model)

    def get_member(self, room_id: int, user_id: int) -> Optional[RoomMember]:
        model = self.db.query(RoomMemberModel).filter(
            RoomMemberModel.room_id == room_id,
            RoomMemberModel.user_id == user_id
        ).first()
        return self._to_member_entity(model)

    def list_members(self, room_id: int) -> List[Tuple[RoomMember, User]]:
        rows = (
            self.db.query(RoomMemberModel, UserModel)
            .join(UserModel, UserModel.id == RoomMemberModel.user_id)
            .filter(RoomMemberModel.room_id == room_id)
            .order_by(RoomMemberModel.role.asc(), UserModel.username.asc())
            .all()
        )
        return [(self._to_member_entity(m), self._to_user_entity(u)) for m, u in rows]

    def update_member_role(self, room_id: int, user_id: int, role: str) -> Optional[RoomMember]:
        model = self.db.query(RoomMemberModel).filter(
            RoomMemberModel.room_id == room_id,
            RoomMemberModel.user_id == user_id
        ).first()
        if not model:
            return None
        model.role = role
        self.db.commit()
        self.db.refresh(model)
        return self._to_member_entity(model)

    def remove_member(self, room_id: int, user_id: int) -> bool:
        deleted = self.db.query(RoomMemberModel).filter(
            RoomMemberModel.room_id == room_id,
            RoomMemberModel.user_id == user_id
        ).delete(synchronize_session=False)
        self.db.commit()
        return deleted > 0

    def count_members(self, room_id: int) -> int:
        return (
            self.db.query(func.count(RoomMemberModel.id))
            .filter(RoomMemberModel.room_id == room_id)
            .scalar()
        ) or 0

    def get_last_message_summary(self, room_id: int) -> Optional[dict]:
        row = (
            self.db.query(MessageModel, UserModel, AttachmentModel)
            .join(UserModel, UserModel.id == MessageModel.user_id)
            .outerjoin(AttachmentModel, AttachmentModel.id == MessageModel.attachment_id)
            .filter(MessageModel.room_id == room_id)
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .first()
        )
        if not row:
            return None
        message, user, attachment = row
        return {
            "id": message.id,
            "content": "" if message.is_deleted else message.content,
            "sender_name": f"{user.last_name} {user.first_name}".strip(),
            "created_at": message.created_at,
            "type": message.message_type,
            "is_deleted": message.is_deleted,
            "attachment_filename": attachment.filename if attachment else None,
        }

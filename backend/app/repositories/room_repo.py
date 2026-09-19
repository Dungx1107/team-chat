from typing import List, Optional
from sqlalchemy.orm import Session
from app.domain.interfaces import IRoomRepository
from app.domain.models import Room, RoomMember
from app.infra.db.models import RoomModel, RoomMemberModel

class RoomRepository(IRoomRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_room_entity(self, model: Optional[RoomModel]) -> Optional[Room]:
        if not model:
            return None
        return Room(
            id=model.id,
            name=model.name,
            owner_id=model.owner_id,
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

    def create(self, room: Room) -> Room:
        model = RoomModel(
            name=room.name,
            owner_id=room.owner_id,
            created_at=room.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_room_entity(model)

    def get_by_id(self, room_id: int) -> Optional[Room]:
        model = self.db.query(RoomModel).filter(RoomModel.id == room_id).first()
        return self._to_room_entity(model)

    def list_all(self, limit: int = 50, offset: int = 0) -> List[Room]:
        models = self.db.query(RoomModel).order_by(RoomModel.created_at.desc()).offset(offset).limit(limit).all()
        return [self._to_room_entity(m) for m in models]

    def delete(self, room_id: int) -> bool:
        model = self.db.query(RoomModel).filter(RoomModel.id == room_id).first()
        if not model:
            return False
        self.db.delete(model)
        self.db.commit()
        return True

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

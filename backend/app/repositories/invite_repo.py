from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.infra.db.models import RoomInviteModel


class InviteRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, invite_id: int) -> Optional[RoomInviteModel]:
        return self.db.query(RoomInviteModel).filter(RoomInviteModel.id == invite_id).first()

    def pending_for_user(self, user_id: int) -> List[RoomInviteModel]:
        return (
            self.db.query(RoomInviteModel)
            .filter(
                RoomInviteModel.invitee_id == user_id,
                RoomInviteModel.status == "PENDING",
            )
            .order_by(RoomInviteModel.created_at.desc())
            .all()
        )

    def pending_for_room_user(self, room_id: int, user_id: int) -> Optional[RoomInviteModel]:
        return (
            self.db.query(RoomInviteModel)
            .filter(
                RoomInviteModel.room_id == room_id,
                RoomInviteModel.invitee_id == user_id,
                RoomInviteModel.status == "PENDING",
            )
            .first()
        )

    def create(self, room_id: int, inviter_id: int, invitee_id: int) -> RoomInviteModel:
        invite = RoomInviteModel(
            room_id=room_id,
            inviter_id=inviter_id,
            invitee_id=invitee_id,
        )
        self.db.add(invite)
        self.db.commit()
        self.db.refresh(invite)
        return invite

    def respond(self, invite: RoomInviteModel, status: str) -> RoomInviteModel:
        invite.status = status
        invite.responded_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(invite)
        return invite

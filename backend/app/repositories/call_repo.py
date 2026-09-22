from typing import List, Optional
from sqlalchemy.orm import Session
from app.domain.interfaces import ICallRepository
from app.domain.models import Call, CallParticipant
from app.infra.db.models import CallModel, CallParticipantModel


class CallRepository(ICallRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: Optional[CallModel]) -> Optional[Call]:
        if not model:
            return None
        return Call(
            id=model.id,
            room_id=model.room_id,
            initiator_id=model.initiator_id,
            kind=model.kind,
            status=model.status,
            created_at=model.created_at,
            answered_at=model.answered_at,
            ended_at=model.ended_at,
            participants=[
                CallParticipant(
                    id=p.id,
                    call_id=p.call_id,
                    user_id=p.user_id,
                    state=p.state,
                    joined_at=p.joined_at,
                    left_at=p.left_at,
                )
                for p in sorted(model.participants, key=lambda p: p.id or 0)
            ],
        )

    def create(self, call: Call) -> Call:
        model = CallModel(
            room_id=call.room_id,
            initiator_id=call.initiator_id,
            kind=call.kind,
            status=call.status,
            created_at=call.created_at,
            answered_at=call.answered_at,
            ended_at=call.ended_at,
        )
        model.participants = [
            CallParticipantModel(
                user_id=p.user_id,
                state=p.state,
                joined_at=p.joined_at,
                left_at=p.left_at,
            )
            for p in call.participants
        ]
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def get_by_id(self, call_id: int) -> Optional[Call]:
        model = self.db.query(CallModel).filter(CallModel.id == call_id).first()
        return self._to_entity(model)

    def save(self, call: Call) -> Call:
        model = self.db.query(CallModel).filter(CallModel.id == call.id).first()
        if not model:
            raise ValueError("Cuộc gọi không tồn tại")
        model.status = call.status
        model.answered_at = call.answered_at
        model.ended_at = call.ended_at

        by_user = {p.user_id: p for p in call.participants}
        for pm in model.participants:
            p = by_user.get(pm.user_id)
            if p:
                pm.state = p.state
                pm.joined_at = p.joined_at
                pm.left_at = p.left_at

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def find_open_call_of_user(self, user_id: int) -> Optional[Call]:
        model = (
            self.db.query(CallModel)
            .join(CallParticipantModel, CallParticipantModel.call_id == CallModel.id)
            .filter(
                CallParticipantModel.user_id == user_id,
                CallModel.status.in_(Call.OPEN_STATUSES),
            )
            .order_by(CallModel.created_at.desc())
            .first()
        )
        return self._to_entity(model)

    def list_by_user(self, user_id: int, limit: int = 30) -> List[Call]:
        models = (
            self.db.query(CallModel)
            .join(CallParticipantModel, CallParticipantModel.call_id == CallModel.id)
            .filter(CallParticipantModel.user_id == user_id)
            .order_by(CallModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_entity(m) for m in models]

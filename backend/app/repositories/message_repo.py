from typing import List
from sqlalchemy.orm import Session
from app.domain.interfaces import IMessageRepository
from app.domain.models import Message
from app.infra.db.models import MessageModel

class MessageRepository(IMessageRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: MessageModel) -> Message:
        return Message(
            id=model.id,
            room_id=model.room_id,
            user_id=model.user_id,
            content=model.content,
            created_at=model.created_at,
        )

    def create(self, message: Message) -> Message:
        model = MessageModel(
            room_id=message.room_id,
            user_id=message.user_id,
            content=message.content,
            created_at=message.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    def get_by_room_id(self, room_id: int, limit: int = 50, offset: int = 0) -> List[Message]:
        models = (
            self.db.query(MessageModel)
            .filter(MessageModel.room_id == room_id)
            .order_by(MessageModel.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_entity(m) for m in models]

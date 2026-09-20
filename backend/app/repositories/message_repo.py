from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from app.domain.interfaces import (
    IMessageRepository,
    IAttachmentRepository,
    IReactionRepository,
)
from app.domain.models import Message, Attachment, Reaction
from app.infra.db.models import (
    MessageModel,
    AttachmentModel,
    ReactionModel,
    UserModel,
)


def _attachment_to_entity(model: Optional[AttachmentModel]) -> Optional[Attachment]:
    if not model:
        return None
    return Attachment(
        id=model.id,
        filename=model.filename,
        stored_name=model.stored_name,
        content_type=model.content_type,
        size_bytes=model.size_bytes,
        uploaded_by=model.uploaded_by,
        created_at=model.created_at,
    )


def _reaction_to_entity(model: ReactionModel) -> Reaction:
    return Reaction(
        id=model.id,
        message_id=model.message_id,
        user_id=model.user_id,
        emoji=model.emoji,
        created_at=model.created_at,
    )


class MessageRepository(IMessageRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: MessageModel, sender: Optional[UserModel] = None) -> Message:
        user = sender if sender is not None else model.sender
        entity = Message.__new__(Message)  # bỏ qua __init__ để không kích hoạt lại validate
        entity.id = model.id
        entity.room_id = model.room_id
        entity.user_id = model.user_id
        entity.content = model.content
        entity.message_type = model.message_type
        entity.attachment_id = model.attachment_id
        entity.created_at = model.created_at
        entity.edited_at = model.edited_at
        entity.is_deleted = model.is_deleted
        entity.sender_name = f"{user.last_name} {user.first_name}".strip() if user else None
        entity.username = user.username if user else None
        entity.avatar_url = user.avatar_url if user else None
        entity.attachment = _attachment_to_entity(model.attachment)
        entity.reactions = [_reaction_to_entity(r) for r in model.reactions]
        return entity

    def create(self, message: Message) -> Message:
        model = MessageModel(
            room_id=message.room_id,
            user_id=message.user_id,
            content=message.content,
            message_type=message.message_type,
            attachment_id=message.attachment_id,
            created_at=message.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self.get_by_id(model.id)

    def get_by_id(self, message_id: int) -> Optional[Message]:
        model = (
            self.db.query(MessageModel)
            .options(
                joinedload(MessageModel.sender),
                joinedload(MessageModel.attachment),
                joinedload(MessageModel.reactions),
            )
            .filter(MessageModel.id == message_id)
            .first()
        )
        return self._to_entity(model) if model else None

    def get_by_room_id(self, room_id: int, limit: int = 50, offset: int = 0) -> List[Message]:
        """Nạp sẵn người gửi, tệp đính kèm và biểu cảm trong cùng một truy vấn.

        Nếu không eager load, mỗi tin nhắn sẽ sinh thêm 3 truy vấn phụ
        (bài toán N+1) -- với 50 tin nhắn là 151 truy vấn thay vì 1.
        """
        models = (
            self.db.query(MessageModel)
            .options(
                joinedload(MessageModel.sender),
                joinedload(MessageModel.attachment),
                joinedload(MessageModel.reactions),
            )
            .filter(MessageModel.room_id == room_id)
            .order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_entity(m) for m in models]

    def update(self, message: Message) -> Message:
        model = self.db.query(MessageModel).filter(MessageModel.id == message.id).first()
        if not model:
            raise ValueError("Tin nhắn không tồn tại")
        model.content = message.content
        model.edited_at = message.edited_at
        model.is_deleted = message.is_deleted
        self.db.commit()
        return self.get_by_id(model.id)

    def soft_delete(self, message_id: int) -> bool:
        model = self.db.query(MessageModel).filter(MessageModel.id == message_id).first()
        if not model:
            return False
        model.is_deleted = True
        model.content = ""
        self.db.commit()
        return True


class AttachmentRepository(IAttachmentRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, attachment: Attachment) -> Attachment:
        model = AttachmentModel(
            filename=attachment.filename,
            stored_name=attachment.stored_name,
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
            uploaded_by=attachment.uploaded_by,
            created_at=attachment.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _attachment_to_entity(model)

    def get_by_id(self, attachment_id: int) -> Optional[Attachment]:
        model = self.db.query(AttachmentModel).filter(AttachmentModel.id == attachment_id).first()
        return _attachment_to_entity(model)


class ReactionRepository(IReactionRepository):
    def __init__(self, db: Session):
        self.db = db

    def add(self, reaction: Reaction) -> Reaction:
        model = ReactionModel(
            message_id=reaction.message_id,
            user_id=reaction.user_id,
            emoji=reaction.emoji,
            created_at=reaction.created_at,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _reaction_to_entity(model)

    def get(self, message_id: int, user_id: int, emoji: str) -> Optional[Reaction]:
        model = self.db.query(ReactionModel).filter(
            ReactionModel.message_id == message_id,
            ReactionModel.user_id == user_id,
            ReactionModel.emoji == emoji,
        ).first()
        return _reaction_to_entity(model) if model else None

    def remove(self, message_id: int, user_id: int, emoji: str) -> bool:
        deleted = self.db.query(ReactionModel).filter(
            ReactionModel.message_id == message_id,
            ReactionModel.user_id == user_id,
            ReactionModel.emoji == emoji,
        ).delete(synchronize_session=False)
        self.db.commit()
        return deleted > 0

    def list_by_message(self, message_id: int) -> List[Reaction]:
        models = self.db.query(ReactionModel).filter(
            ReactionModel.message_id == message_id
        ).all()
        return [_reaction_to_entity(m) for m in models]

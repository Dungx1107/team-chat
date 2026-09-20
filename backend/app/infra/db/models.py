from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    UniqueConstraint, Boolean, BigInteger, Index
)
from sqlalchemy.orm import relationship
from app.infra.db.session import Base

class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Hồ sơ cá nhân
    avatar_url = Column(String(255), nullable=True)
    bio = Column(String(500), nullable=True)
    status = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Quan hệ
    refresh_tokens = relationship("RefreshTokenModel", back_populates="user", cascade="all, delete-orphan")
    owned_rooms = relationship("RoomModel", back_populates="owner", cascade="all, delete-orphan")
    memberships = relationship("RoomMemberModel", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("MessageModel", back_populates="sender", cascade="all, delete-orphan")


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("UserModel", back_populates="refresh_tokens")


class RoomModel(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    description = Column(String(300), nullable=True)
    is_private = Column(Boolean, default=False, nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    owner = relationship("UserModel", back_populates="owned_rooms")
    members = relationship("RoomMemberModel", back_populates="room", cascade="all, delete-orphan")
    messages = relationship("MessageModel", back_populates="room", cascade="all, delete-orphan")


class RoomMemberModel(Base):
    __tablename__ = "room_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), default="MEMBER", nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_room_member"),
    )

    room = relationship("RoomModel", back_populates="members")
    user = relationship("UserModel", back_populates="memberships")


class AttachmentModel(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    stored_name = Column(String(255), unique=True, nullable=False, index=True)
    content_type = Column(String(120), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False, default="")
    message_type = Column(String(20), default="TEXT", nullable=False)
    attachment_id = Column(Integer, ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    edited_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        # Truy vấn nóng nhất là "lấy tin nhắn mới nhất của một phòng"
        Index("ix_messages_room_created", "room_id", "created_at"),
    )

    room = relationship("RoomModel", back_populates="messages")
    sender = relationship("UserModel", back_populates="messages")
    attachment = relationship("AttachmentModel", lazy="joined")
    reactions = relationship("ReactionModel", back_populates="message", cascade="all, delete-orphan")


class ReactionModel(Base):
    __tablename__ = "reactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    emoji = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # Mỗi người chỉ thả được một lần cho mỗi loại biểu cảm trên một tin nhắn
        UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction_once"),
    )

    message = relationship("MessageModel", back_populates="reactions")

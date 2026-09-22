from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class MessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)

class AttachmentResponse(BaseModel):
    id: int
    filename: str
    content_type: str
    size_bytes: int
    kind: str

class ReactionSummary(BaseModel):
    emoji: str
    count: int
    user_ids: List[int]

class MessageResponse(BaseModel):
    id: int
    room_id: int
    user_id: int
    content: str
    message_type: str = "TEXT"
    created_at: datetime
    edited_at: Optional[datetime] = None
    is_deleted: bool = False
    sender_name: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    attachment: Optional[AttachmentResponse] = None
    reactions: List[ReactionSummary] = []

    class Config:
        from_attributes = True

class ReactionRequest(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=16)

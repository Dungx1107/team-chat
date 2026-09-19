from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class MessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)

class MessageResponse(BaseModel):
    id: int
    room_id: int
    user_id: int
    content: str
    created_at: datetime
    sender_name: Optional[str] = None
    username: Optional[str] = None

    class Config:
        from_attributes = True
from datetime import datetime
from pydantic import BaseModel, Field

class RoomCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)

class RoomResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    created_at: datetime

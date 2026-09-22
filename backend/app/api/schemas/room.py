from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class RoomCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=300)
    is_private: bool = False

class RoomUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=300)

class RoomResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_private: bool = False
    owner_id: int
    created_at: datetime
    my_role: Optional[str] = None
    member_count: Optional[int] = None
    avatar_url: Optional[str] = None
    last_message: Optional[dict] = None
    unread_count: int = 0

class MemberResponse(BaseModel):
    user_id: int
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    status: Optional[str] = None
    role: str
    joined_at: datetime
    is_online: bool = False

class AddMemberRequest(BaseModel):
    user_id: int

class ChangeRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(ADMIN|MEMBER)$")

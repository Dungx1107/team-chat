from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class ProfileResponse(BaseModel):
    id: int
    email: str
    username: str
    first_name: str
    last_name: str
    full_name: str
    initials: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    status: Optional[str] = None
    is_active: bool
    created_at: datetime

class PublicProfileResponse(BaseModel):
    """Hồ sơ rút gọn khi xem người khác -- không lộ email."""
    id: int
    username: str
    full_name: str
    initials: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    status: Optional[str] = None

class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    bio: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, max_length=100)

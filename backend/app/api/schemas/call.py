from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class CallStartRequest(BaseModel):
    callee_id: int
    room_id: int
    kind: str = Field("VIDEO", pattern="^(AUDIO|VIDEO)$")


class CallEndRequest(BaseModel):
    # true khi người gọi dập máy vì hết thời gian chờ -> ghi nhận là cuộc gọi nhỡ
    missed: bool = False


class CallParticipantResponse(BaseModel):
    id: int
    full_name: str
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    state: str


class CallResponse(BaseModel):
    id: int
    room_id: Optional[int] = None
    kind: str
    status: str
    initiator_id: int
    created_at: datetime
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    participants: List[CallParticipantResponse]


class IceConfigResponse(BaseModel):
    ice_servers: List[dict]
    ring_timeout_seconds: int

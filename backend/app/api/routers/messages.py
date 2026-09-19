from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from app.api.schemas import MessageCreateRequest, MessageResponse
from app.api.dependencies import get_message_service, get_current_user_id
from app.services.message_service import MessageService

router = APIRouter(prefix="/rooms/{room_id}/messages", tags=["Messages"])

@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def send_message(
    room_id: int,
    body: MessageCreateRequest,
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service)
):
    try:
        msg = msg_service.send_message(
            room_id=room_id,
            user_id=current_user_id,
            content=body.content
        )
        return MessageResponse(
            id=msg.id,
            room_id=msg.room_id,
            user_id=msg.user_id,
            content=msg.content,
            created_at=msg.created_at
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("", response_model=List[MessageResponse])
def get_messages(
    room_id: int,
    limit: int = 50,
    offset: int = 0,
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service)
):
    try:
        messages = msg_service.get_room_messages(room_id=room_id, limit=limit, offset=offset)
        return [
            MessageResponse(
                id=m.id,
                room_id=m.room_id,
                user_id=m.user_id,
                content=m.content,
                created_at=m.created_at
            )
            for m in messages
        ]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

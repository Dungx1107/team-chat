from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from app.api.schemas import RoomCreateRequest, RoomResponse
from app.api.dependencies import get_room_service, get_current_user_id
from app.services.room_service import RoomService

router = APIRouter(prefix="/rooms", tags=["Rooms"])

@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def create_room(
    body: RoomCreateRequest,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    try:
        room = room_service.create_room(name=body.name, owner_id=current_user_id)
        return RoomResponse(
            id=room.id,
            name=room.name,
            owner_id=room.owner_id,
            created_at=room.created_at
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("", response_model=List[RoomResponse])
def list_rooms(
    limit: int = 50,
    offset: int = 0,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    rooms = room_service.list_rooms(limit=limit, offset=offset)
    return [
        RoomResponse(
            id=r.id,
            name=r.name,
            owner_id=r.owner_id,
            created_at=r.created_at
        )
        for r in rooms
    ]

@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    try:
        room_service.delete_room(room_id=room_id, user_id=current_user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

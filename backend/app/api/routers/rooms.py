from typing import List
import mimetypes
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from app.api.schemas import (
    RoomCreateRequest,
    RoomUpdateRequest,
    RoomResponse,
    MemberResponse,
    AddMemberRequest,
    ChangeRoleRequest,
)
from app.api.dependencies import get_room_service, get_current_user_id, get_call_service, file_storage
from app.services.room_service import RoomService
from app.infra.realtime.connection_manager import connection_manager

router = APIRouter(prefix="/rooms", tags=["Rooms"])


def _to_response(room, my_role=None, member_count=None, last_message=None, unread_count=0) -> RoomResponse:
    return RoomResponse(
        id=room.id,
        name=room.name,
        description=room.description,
        is_private=room.is_private,
        owner_id=room.owner_id,
        created_at=room.created_at,
        my_role=my_role,
        member_count=member_count,
        avatar_url=getattr(room, "avatar_url", None),
        last_message=last_message,
        unread_count=unread_count,
    )


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def create_room(
    body: RoomCreateRequest,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    try:
        room = room_service.create_room(
            name=body.name,
            owner_id=current_user_id,
            description=body.description,
            is_private=body.is_private,
        )
        return _to_response(room, my_role="OWNER", member_count=1)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=List[RoomResponse])
def list_rooms(
    limit: int = 50,
    offset: int = 0,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    """Phòng công khai, cộng thêm phòng riêng tư mà người dùng là thành viên."""
    rooms = room_service.list_rooms(user_id=current_user_id, limit=limit, offset=offset)
    result = []
    for r in rooms:
        member = room_service.room_repo.get_member(r.id, current_user_id)
        result.append(_to_response(
            r,
            my_role=member.role if member else None,
            member_count=room_service.room_repo.count_members(r.id),
            last_message=room_service.room_repo.get_last_message_summary(r.id),
        ))
    return result


@router.get("/{room_id}", response_model=RoomResponse)
def get_room(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    try:
        room = room_service.get_room(room_id, current_user_id)
        member = room_service.room_repo.get_member(room_id, current_user_id)
        return _to_response(
            room,
            my_role=member.role if member else None,
            member_count=room_service.room_repo.count_members(room_id),
            last_message=room_service.room_repo.get_last_message_summary(room_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{room_id}", response_model=RoomResponse)
def update_room(
    room_id: int,
    body: RoomUpdateRequest,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    try:
        room = room_service.update_room(
            room_id=room_id,
            user_id=current_user_id,
            name=body.name,
            description=body.description,
        )
        member = room_service.room_repo.get_member(room_id, current_user_id)
        return _to_response(room, my_role=member.role if member else None)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


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


@router.post("/{room_id}/avatar", response_model=RoomResponse)
def upload_room_avatar(
    room_id: int,
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service),
):
    try:
        room = room_service.update_avatar(
            room_id, current_user_id, file.file, file.filename or "room-avatar.png",
            file.content_type or "application/octet-stream",
        )
        member = room_service.room_repo.get_member(room_id, current_user_id)
        return _to_response(room, member.role if member else None, room_service.room_repo.count_members(room_id))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/{room_id}/avatar")
def get_room_avatar(room_id: int, room_service: RoomService = Depends(get_room_service)):
    try:
        room = room_service._get_room_or_fail(room_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if not room.avatar_url or not file_storage.exists(room.avatar_url):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phòng chưa có avatar")
    mime_type = mimetypes.guess_type(room.avatar_url)[0] or "application/octet-stream"
    return StreamingResponse(file_storage.open_stream(room.avatar_url), media_type=mime_type)


# ---------- Thành viên và phân quyền ----------

@router.get("/{room_id}/active-call")
def get_active_group_call(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    call_service=Depends(get_call_service),
):
    """Phòng này có cuộc gọi nhóm đang diễn ra không, để hiện nút Tham gia."""
    try:
        call = call_service.get_active_group_call(room_id, current_user_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return call_service.to_payload(call) if call else None


@router.post("/{room_id}/join", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def join_room(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    try:
        room_service.join_room(room_id, current_user_id)
        return _find_member_response(room_service, room_id, current_user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/{room_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_room(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    try:
        room_service.leave_room(room_id, current_user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/{room_id}/members", response_model=List[MemberResponse])
def list_members(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    try:
        pairs = room_service.list_members(room_id, current_user_id)
        return [
            MemberResponse(
                user_id=u.id,
                username=u.username,
                full_name=u.full_name,
                avatar_url=u.avatar_url,
                status=u.status,
                role=m.role,
                joined_at=m.joined_at,
                is_online=connection_manager.is_online(u.id),
            )
            for m, u in pairs
        ]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/{room_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(
    room_id: int,
    body: AddMemberRequest,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    """Mời người dùng vào phòng -- cách duy nhất để vào phòng riêng tư."""
    try:
        room_service.add_member(room_id, current_user_id, body.user_id)
        return _find_member_response(room_service, room_id, body.user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/{room_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    room_id: int,
    user_id: int,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    try:
        room_service.remove_member(room_id, current_user_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{room_id}/members/{user_id}/role", response_model=MemberResponse)
def change_member_role(
    room_id: int,
    user_id: int,
    body: ChangeRoleRequest,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service)
):
    """Phong hoặc giáng vai trò thành viên. Chỉ chủ phòng có quyền này."""
    try:
        room_service.change_member_role(room_id, current_user_id, user_id, body.role)
        return _find_member_response(room_service, room_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


def _find_member_response(room_service: RoomService, room_id: int, user_id: int) -> MemberResponse:
    for m, u in room_service.room_repo.list_members(room_id):
        if u.id == user_id:
            return MemberResponse(
                user_id=u.id,
                username=u.username,
                full_name=u.full_name,
                avatar_url=u.avatar_url,
                status=u.status,
                role=m.role,
                joined_at=m.joined_at,
                is_online=connection_manager.is_online(u.id),
            )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thành viên")

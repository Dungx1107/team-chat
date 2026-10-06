from typing import List
import mimetypes
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from app.api.schemas import (
    RoomCreateRequest,
    RoomUpdateRequest,
    RoomResponse,
    MemberResponse,
    AddMemberRequest,
    ChangeRoleRequest,
    NicknameUpdateRequest,
)
from app.api.dependencies import (
    get_room_service,
    get_current_user_id,
    get_call_service,
    get_message_service,
    file_storage,
    get_db,
)
from app.services.room_service import RoomService
from app.services.message_service import MessageService
from app.infra.realtime.connection_manager import connection_manager
from app.repositories.invite_repo import InviteRepository
from app.repositories.user_repo import UserRepository
from app.repositories.room_repo import RoomRepository
from app.domain.models import RoomMember

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
        theme_color=getattr(room, "theme_color", None),
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
            theme_color=body.theme_color,
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

@router.get("/{room_id}/media")
def list_room_media(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service),
):
    try:
        room_service.get_room(room_id, current_user_id)
        return room_service.room_repo.list_media(room_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


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
                nickname=m.nickname,
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


@router.post("/{room_id}/invites", status_code=status.HTTP_201_CREATED)
def invite_member(
    room_id: int,
    body: AddMemberRequest,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service),
    db: Session = Depends(get_db),
):
    """Tạo lời mời; người nhận phải chấp nhận trước khi trở thành thành viên."""
    try:
        room_service._get_room_or_fail(room_id)
        actor = room_service.require_membership(room_id, current_user_id)
        if not actor.can_manage_members():
            raise PermissionError("Chỉ chủ phòng hoặc quản trị viên mới được mời thành viên")
        if body.user_id == current_user_id:
            raise ValueError("Không thể tự mời chính mình")
        if not UserRepository(db).get_by_id(body.user_id):
            raise ValueError("Người dùng không tồn tại")
        if room_service.room_repo.get_member(room_id, body.user_id):
            raise ValueError("Người dùng đã là thành viên của phòng")
        invites = InviteRepository(db)
        if invites.pending_for_room_user(room_id, body.user_id):
            raise ValueError("Lời mời này đang chờ người dùng phản hồi")
        invite = invites.create(room_id, current_user_id, body.user_id)
        room = room_service.room_repo.get_by_id(room_id)
        inviter = UserRepository(db).get_by_id(current_user_id)
        connection_manager.publish_to_user(body.user_id, "room.invite", {
            "id": invite.id,
            "room_id": room_id,
            "room_name": room.name,
            "inviter_id": current_user_id,
            "inviter_name": inviter.full_name if inviter else "Một thành viên",
            "created_at": invite.created_at,
        })
        return {"id": invite.id, "room_id": room_id, "status": invite.status}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/notifications/invites")
def list_invites(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    invites = InviteRepository(db).pending_for_user(current_user_id)
    rooms = {room.id: room for room in [RoomRepository(db).get_by_id(i.room_id) for i in invites]}
    users = {user.id: user for user in [UserRepository(db).get_by_id(i.inviter_id) for i in invites]}
    return [{
        "id": invite.id,
        "room_id": invite.room_id,
        "room_name": rooms[invite.room_id].name,
        "inviter_id": invite.inviter_id,
        "inviter_name": users[invite.inviter_id].full_name if users.get(invite.inviter_id) else "Một thành viên",
        "created_at": invite.created_at,
    } for invite in invites if rooms.get(invite.room_id)]


@router.post("/notifications/invites/{invite_id}/accept")
def accept_invite(
    invite_id: int,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service),
    msg_service: MessageService = Depends(get_message_service),
    db: Session = Depends(get_db),
):
    invite = InviteRepository(db).get(invite_id)
    if not invite or invite.invitee_id != current_user_id or invite.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lời mời không tồn tại hoặc đã xử lý")
    room = room_service._get_room_or_fail(invite.room_id)
    if not room_service.room_repo.get_member(room.id, current_user_id):
        room_service.room_repo.add_member(RoomMember(room_id=room.id, user_id=current_user_id, role=RoomMember.ROLE_MEMBER))
        room_service._publish_member_event(room.id, current_user_id, "room.member_joined")
        user = UserRepository(db).get_by_id(current_user_id)
        msg_service.create_system_message(room.id, current_user_id, f"{user.full_name if user else 'Một người dùng'} đã vào phòng")
    InviteRepository(db).respond(invite, "ACCEPTED")
    return {"room_id": room.id, "status": "ACCEPTED"}


@router.post("/notifications/invites/{invite_id}/reject")
def reject_invite(
    invite_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    invite = InviteRepository(db).get(invite_id)
    if not invite or invite.invitee_id != current_user_id or invite.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lời mời không tồn tại hoặc đã xử lý")
    InviteRepository(db).respond(invite, "REJECTED")
    return {"status": "REJECTED"}


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

@router.patch("/{room_id}/members/{user_id}/nickname", response_model=MemberResponse)
def update_member_nickname(
    room_id: int,
    user_id: int,
    body: NicknameUpdateRequest,
    current_user_id: int = Depends(get_current_user_id),
    room_service: RoomService = Depends(get_room_service),
    msg_service: MessageService = Depends(get_message_service),
):
    try:
        actor = room_service.require_membership(room_id, current_user_id)
        room_service.require_membership(room_id, user_id)
        members = room_service.room_repo.list_members(room_id)
        actor_user = next((user for member, user in members if member.user_id == current_user_id), None)
        target_user = next((user for member, user in members if member.user_id == user_id), None)
        if not actor_user or not target_user:
            raise ValueError("Không tìm thấy thành viên")
        if not room_service.room_repo.update_member_nickname(room_id, user_id, body.nickname):
            raise ValueError("Không tìm thấy thành viên")
        new_nickname = body.nickname.strip() if body.nickname and body.nickname.strip() else None
        actor_name = f"{actor_user.last_name} {actor_user.first_name}".strip()
        target_name = f"{target_user.last_name} {target_user.first_name}".strip()
        if new_nickname:
            if current_user_id == user_id:
                content = f"{actor_name} đã đặt biệt danh cho mình là {new_nickname}"
            else:
                content = f"{actor_name} đã đặt biệt danh cho {target_name} là {new_nickname}"
        else:
            if current_user_id == user_id:
                content = f"{actor_name} đã xóa biệt danh của mình"
            else:
                content = f"{actor_name} đã xóa biệt danh của {target_name}"
        msg_service.create_system_message(room_id, current_user_id, content)
        msg_service.events.publish_to_room(room_id, "room.nickname_updated", {
            "room_id": room_id,
            "user_id": user_id,
            "nickname": new_nickname,
            "full_name": target_name,
        })
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
                nickname=m.nickname,
                joined_at=m.joined_at,
                is_online=connection_manager.is_online(u.id),
            )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thành viên")

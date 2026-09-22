from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from app.api.schemas import (
    MessageCreateRequest,
    MessageResponse,
    AttachmentResponse,
    ReactionRequest,
    MessageEditRequest,
)
from app.api.dependencies import get_message_service, get_current_user_id, file_storage
from app.services.message_service import MessageService

router = APIRouter(tags=["Messages"])


def _to_response(msg, svc: MessageService) -> MessageResponse:
    attachment = None
    if msg.attachment:
        a = msg.attachment
        attachment = AttachmentResponse(
            id=a.id,
            filename=a.filename,
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            kind=a.kind,
        )
    return MessageResponse(
        id=msg.id,
        room_id=msg.room_id,
        user_id=msg.user_id,
        content=msg.content,
        message_type=msg.message_type,
        created_at=msg.created_at,
        edited_at=msg.edited_at,
        is_deleted=msg.is_deleted,
        reply_to_id=getattr(msg, "reply_to_id", None),
        forwarded_from_id=getattr(msg, "forwarded_from_id", None),
        pinned=getattr(msg, "pinned", False),
        pinned_at=getattr(msg, "pinned_at", None),
        pinned_by=getattr(msg, "pinned_by", None),
        deleted_at=getattr(msg, "deleted_at", None),
        sender_name=msg.sender_name,
        username=msg.username,
        avatar_url=msg.avatar_url,
        attachment=attachment,
        reactions=svc._summarize_reactions(msg.reactions),
    )


@router.post(
    "/rooms/{room_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
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
            content=body.content,
            reply_to_id=body.reply_to_id,
        )
        return _to_response(msg, msg_service)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post(
    "/rooms/{room_id}/messages/upload",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_file_message(
    room_id: int,
    file: UploadFile = File(...),
    caption: str = Form(""),
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service)
):
    """Gửi tin nhắn kèm ảnh, video hoặc tài liệu."""
    try:
        msg = msg_service.send_file_message(
            room_id=room_id,
            user_id=current_user_id,
            file_obj=file.file,
            filename=file.filename or "tep-dinh-kem",
            content_type=file.content_type or "application/octet-stream",
            caption=caption,
        )
        return _to_response(msg, msg_service)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/rooms/{room_id}/messages", response_model=List[MessageResponse])
def get_messages(
    room_id: int,
    limit: int = 50,
    offset: int = 0,
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service)
):
    try:
        messages = msg_service.get_room_messages(
            room_id=room_id,
            user_id=current_user_id,
            limit=limit,
            offset=offset,
        )
        return [_to_response(m, msg_service) for m in messages]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/rooms/{room_id}/pinned-messages", response_model=List[MessageResponse])
def get_pinned_messages(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service),
):
    try:
        messages = msg_service.get_pinned_messages(room_id, current_user_id)
        return [_to_response(message, msg_service) for message in messages]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    message_id: int,
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service)
):
    """Xóa mềm: tự xóa tin của mình, hoặc ADMIN/OWNER xóa tin người khác."""
    try:
        msg_service.delete_message(message_id, current_user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/messages/{message_id}", response_model=MessageResponse)
def edit_message(
    message_id: int,
    body: MessageEditRequest,
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service),
):
    try:
        return _to_response(msg_service.edit_message(message_id, current_user_id, body.content), msg_service)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/messages/{message_id}/pin", response_model=MessageResponse)
def pin_message(
    message_id: int,
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service),
):
    try:
        return _to_response(msg_service.pin_message(message_id, current_user_id), msg_service)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/messages/{message_id}/pin", response_model=MessageResponse)
def unpin_message(
    message_id: int,
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service),
):
    try:
        return _to_response(msg_service.unpin_message(message_id, current_user_id), msg_service)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/messages/{message_id}/reactions")
def toggle_reaction(
    message_id: int,
    body: ReactionRequest,
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service)
):
    """Thả biểu cảm; gọi lại lần nữa với cùng emoji sẽ gỡ biểu cảm đó."""
    try:
        return msg_service.toggle_reaction(message_id, current_user_id, body.emoji)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/attachments/{attachment_id}")
def download_attachment(
    attachment_id: int,
    current_user_id: int = Depends(get_current_user_id),
    msg_service: MessageService = Depends(get_message_service)
):
    try:
        attachment = msg_service.get_attachment(attachment_id, current_user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    if not file_storage.exists(attachment.stored_name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tệp không còn trên hệ thống")

    stream = file_storage.open_stream(attachment.stored_name)
    # Ảnh/video hiển thị ngay trong trình duyệt, tệp khác thì tải về
    disposition = "inline" if attachment.kind in ("IMAGE", "VIDEO", "AUDIO") else "attachment"
    return StreamingResponse(
        stream,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename*=UTF-8\'\'{attachment.filename}',
            "Content-Length": str(attachment.size_bytes),
        },
    )

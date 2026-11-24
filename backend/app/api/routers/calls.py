from typing import List
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from starlette.concurrency import run_in_threadpool
from app.api.schemas.call import (
    CallStartRequest,
    GroupCallStartRequest,
    CallEndRequest,
    CallResponse,
    IceConfigResponse,
    SfuSessionResponse,
)
from app.api.dependencies import (get_call_service, get_current_user_id, get_group_media_service, livekit_gateway)
from app.services.group_media_service import GroupMediaService
from app.config import settings
from app.services.call_service import CallService
from app.domain.models import Call

router = APIRouter(prefix="/calls", tags=["Calls"])

RING_TIMEOUT_SECONDS = 30
logger = logging.getLogger(__name__)


async def _media_handle(operation):
    try:
        return await operation
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.warning("LiveKit request failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Không kết nối được máy chủ cuộc gọi nhóm; hãy thử lại")


def _handle(fn):
    """Ánh xạ lỗi nghiệp vụ sang mã HTTP, dùng chung cho mọi endpoint cuộc gọi."""
    try:
        return fn()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except RuntimeError as e:
        # Đang bận trong cuộc gọi khác
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/config", response_model=IceConfigResponse)
def get_call_config(current_user_id: int = Depends(get_current_user_id)):
    """Cấu hình để trình duyệt dựng kết nối WebRTC."""
    return IceConfigResponse(
        ice_servers=settings.ice_server_list,
        ring_timeout_seconds=RING_TIMEOUT_SECONDS,
        max_group_participants=settings.GROUP_CALL_MAX_PARTICIPANTS,
        group_available=settings.livekit_configured,
    )


@router.post("", response_model=CallResponse, status_code=status.HTTP_201_CREATED)
def start_call(
    body: CallStartRequest,
    current_user_id: int = Depends(get_current_user_id),
    svc: CallService = Depends(get_call_service),
):
    """Bắt đầu gọi 1-1 cho một thành viên cùng phòng. Người nhận nhận sự kiện call.incoming."""
    call = _handle(lambda: svc.start_call(current_user_id, body.callee_id, body.room_id, body.kind))
    return svc.to_payload(call)


@router.post("/group", response_model=CallResponse, status_code=status.HTTP_201_CREATED)
def start_group_call(
    body: GroupCallStartRequest,
    current_user_id: int = Depends(get_current_user_id),
    svc: CallService = Depends(get_call_service),
):
    """Mở cuộc gọi nhóm trong phòng. Không đổ chuông; cả phòng nhận call.room_started.

    Nếu phòng đã có cuộc gọi nhóm đang diễn ra thì tham gia luôn cuộc gọi đó.
    """
    if not settings.livekit_configured:
        raise HTTPException(status_code=503, detail="LiveKit chưa được cấu hình cho cuộc gọi nhóm")
    call = _handle(lambda: svc.start_group_call(current_user_id, body.room_id, body.kind))
    return svc.to_payload(call)


@router.post("/{call_id}/join", response_model=CallResponse)
def join_call(
    call_id: int,
    current_user_id: int = Depends(get_current_user_id),
    svc: CallService = Depends(get_call_service),
):
    """Tham gia cuộc gọi nhóm đang diễn ra."""
    if not settings.livekit_configured:
        raise HTTPException(status_code=503, detail="LiveKit chưa được cấu hình cho cuộc gọi nhóm")
    call = _handle(lambda: svc.join_call(call_id, current_user_id))
    return svc.to_payload(call)


@router.post("/{call_id}/leave", response_model=CallResponse)
async def leave_call(
    call_id: int,
    current_user_id: int = Depends(get_current_user_id),
    svc: CallService = Depends(get_call_service),
    media: GroupMediaService = Depends(get_group_media_service),
):
    """Rời cuộc gọi nhóm. Người cuối cùng rời đi thì cuộc gọi kết thúc."""
    call = await _media_handle(media.leave(call_id, current_user_id))
    return svc.to_payload(call)


@router.post("/{call_id}/sfu-session", response_model=SfuSessionResponse)
async def sfu_session(call_id: int, response: Response,
                      current_user_id: int = Depends(get_current_user_id),
                      media: GroupMediaService = Depends(get_group_media_service)):
    response.headers["Cache-Control"] = "no-store"
    return await _media_handle(media.session(call_id, current_user_id))


@router.post("/{call_id}/sfu-sync", response_model=CallResponse)
async def sfu_sync(call_id: int, current_user_id: int = Depends(get_current_user_id),
                   media: GroupMediaService = Depends(get_group_media_service)):
    await run_in_threadpool(lambda: _handle(lambda: media.calls.require_sfu_admission(call_id, current_user_id)))
    call = await _media_handle(media.sync(call_id))
    return await run_in_threadpool(media.calls.to_payload, call)


@router.post("/livekit/webhook", include_in_schema=False)
async def livekit_webhook(request: Request, media: GroupMediaService = Depends(get_group_media_service)):
    if not settings.livekit_configured:
        raise HTTPException(status_code=503, detail="LiveKit chưa được cấu hình")
    if int(request.headers.get("content-length", "0")) > 256 * 1024:
        raise HTTPException(status_code=413, detail="Webhook quá lớn")
    raw = await request.body()
    if len(raw) > 256 * 1024:
        raise HTTPException(status_code=413, detail="Webhook quá lớn")
    try:
        event = livekit_gateway.verify_webhook(raw.decode("utf-8"), request.headers.get("Authorization", ""))
    except Exception:
        raise HTTPException(status_code=401, detail="Chữ ký webhook không hợp lệ")
    call_id = livekit_gateway.call_id(event.room.name)
    if call_id is not None:
        call = await run_in_threadpool(media.calls.call_repo.get_by_id, call_id)
        if call and call.is_group():
            # Xác minh snapshot thay vì áp dụng delta: lặp/trễ không làm sai phiên mới.
            await _media_handle(media.sync(call_id))
    return Response(status_code=204)


@router.get("", response_model=List[CallResponse])
def list_calls(
    limit: int = 30,
    current_user_id: int = Depends(get_current_user_id),
    svc: CallService = Depends(get_call_service),
):
    """Lịch sử cuộc gọi của người dùng hiện tại."""
    return [svc.to_payload(c) for c in svc.list_history(current_user_id, limit=limit)]


@router.get("/{call_id}", response_model=CallResponse)
def get_call(
    call_id: int,
    current_user_id: int = Depends(get_current_user_id),
    svc: CallService = Depends(get_call_service),
):
    call = _handle(lambda: svc.get_call(call_id, current_user_id))
    return svc.to_payload(call)


@router.post("/{call_id}/accept", response_model=CallResponse)
def accept_call(
    call_id: int,
    current_user_id: int = Depends(get_current_user_id),
    svc: CallService = Depends(get_call_service),
):
    call = _handle(lambda: svc.accept_call(call_id, current_user_id))
    return svc.to_payload(call)


@router.post("/{call_id}/decline", response_model=CallResponse)
def decline_call(
    call_id: int,
    current_user_id: int = Depends(get_current_user_id),
    svc: CallService = Depends(get_call_service),
):
    call = _handle(lambda: svc.decline_call(call_id, current_user_id))
    return svc.to_payload(call)


@router.post("/{call_id}/end", response_model=CallResponse)
def end_call(
    call_id: int,
    body: CallEndRequest = CallEndRequest(),
    current_user_id: int = Depends(get_current_user_id),
    svc: CallService = Depends(get_call_service),
):
    """Dập máy. Đang đổ chuông thì thành hủy/nhỡ, đang nói chuyện thì thành kết thúc."""
    call = _handle(lambda: svc.end_call(call_id, current_user_id, missed=body.missed))
    return svc.to_payload(call)

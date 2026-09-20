from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from app.api.schemas import (
    ProfileResponse,
    PublicProfileResponse,
    ProfileUpdateRequest,
)
from app.api.dependencies import get_user_service, get_current_user_id, file_storage
from app.services.user_service import UserService
from app.infra.realtime.connection_manager import connection_manager

router = APIRouter(prefix="/users", tags=["Users"])


def _to_profile(user) -> ProfileResponse:
    return ProfileResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        initials=user.initials,
        avatar_url=user.avatar_url,
        bio=user.bio,
        status=user.status,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _to_public(user) -> PublicProfileResponse:
    return PublicProfileResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        initials=user.initials,
        avatar_url=user.avatar_url,
        bio=user.bio,
        status=user.status,
    )


@router.get("/me", response_model=ProfileResponse)
def get_my_profile(
    current_user_id: int = Depends(get_current_user_id),
    user_service: UserService = Depends(get_user_service)
):
    try:
        return _to_profile(user_service.get_profile(current_user_id))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/me", response_model=ProfileResponse)
def update_my_profile(
    body: ProfileUpdateRequest,
    current_user_id: int = Depends(get_current_user_id),
    user_service: UserService = Depends(get_user_service)
):
    try:
        user = user_service.update_profile(
            user_id=current_user_id,
            first_name=body.first_name,
            last_name=body.last_name,
            bio=body.bio,
            status=body.status,
        )
        return _to_profile(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/me/avatar", response_model=ProfileResponse)
def upload_avatar(
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id),
    user_service: UserService = Depends(get_user_service)
):
    try:
        user = user_service.update_avatar(
            user_id=current_user_id,
            file_obj=file.file,
            filename=file.filename or "avatar.png",
            content_type=file.content_type or "application/octet-stream",
        )
        return _to_profile(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/search", response_model=List[PublicProfileResponse])
def search_users(
    q: str,
    limit: int = 20,
    current_user_id: int = Depends(get_current_user_id),
    user_service: UserService = Depends(get_user_service)
):
    """Tìm người dùng để mời vào phòng riêng tư."""
    return [_to_public(u) for u in user_service.search_users(q, limit=limit)]


@router.get("/online", response_model=List[int])
def list_online_users(current_user_id: int = Depends(get_current_user_id)):
    return sorted(connection_manager.online_user_ids())


@router.get("/{user_id}", response_model=PublicProfileResponse)
def get_user_profile(
    user_id: int,
    current_user_id: int = Depends(get_current_user_id),
    user_service: UserService = Depends(get_user_service)
):
    try:
        return _to_public(user_service.get_profile(user_id))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{user_id}/avatar")
def get_user_avatar(
    user_id: int,
    user_service: UserService = Depends(get_user_service)
):
    """Ảnh đại diện. Để công khai để thẻ <img> tải được mà không cần header."""
    try:
        user = user_service.get_profile(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người dùng không tồn tại")

    if not user.avatar_url or not file_storage.exists(user.avatar_url):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chưa có ảnh đại diện")

    return StreamingResponse(
        file_storage.open_stream(user.avatar_url),
        media_type="image/*",
        headers={"Cache-Control": "public, max-age=300"},
    )

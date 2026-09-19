from fastapi import APIRouter, Depends, HTTPException, status
from app.api.schemas import RegisterRequest, LoginRequest, RefreshTokenRequest, TokenResponse, UserResponse
from app.api.dependencies import get_auth_service
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, auth_service: AuthService = Depends(get_auth_service)):
    try:
        user = auth_service.register(
            email=body.email,
            username=body.username,
            password=body.password,
            first_name=body.first_name,
            last_name=body.last_name
        )
        return UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, auth_service: AuthService = Depends(get_auth_service)):
    try:
        result = auth_service.login(email=body.email, password=body.password)
        u = result["user"]
        return TokenResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            token_type=result["token_type"],
            user=UserResponse(
                id=u.id,
                email=u.email,
                username=u.username,
                first_name=u.first_name,
                last_name=u.last_name,
                full_name=u.full_name,
                is_active=u.is_active,
                created_at=u.created_at
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@router.post("/refresh")
def refresh_token(body: RefreshTokenRequest, auth_service: AuthService = Depends(get_auth_service)):
    try:
        return auth_service.rotate_refresh_token(body.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

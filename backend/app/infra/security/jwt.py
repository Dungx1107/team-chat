import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from app.config import settings

def create_access_token(subject: int, expires_delta: Optional[timedelta] = None) -> str:
    """Tạo JWT Access Token sống ngắn (mặc định 60 phút để thoải mái test)"""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=60))
    payload = {
        "sub": str(subject),
        "exp": int(expire.timestamp()),
        "type": "access"
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def generate_refresh_token() -> str:
    return secrets.token_hex(32)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.PyJWTError:
        return None

from app.api.routers.auth import router as auth_router
from app.api.routers.rooms import router as rooms_router
from app.api.routers.messages import router as messages_router
from app.api.routers.users import router as users_router
from app.api.routers.ws import router as ws_router

__all__ = [
    "auth_router",
    "rooms_router",
    "messages_router",
    "users_router",
    "ws_router",
]

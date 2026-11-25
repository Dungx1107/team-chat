"""LiveKit adapter: dùng cùng media API cho self-hosted và Cloud."""
from datetime import datetime, timedelta, timezone
import time

import aiohttp
from livekit import api

from app.config import Settings


class LiveKitGateway:
    def __init__(self, settings: Settings):
        self.settings = settings

    def require_configured(self):
        if not self.settings.livekit_configured:
            raise RuntimeError("LiveKit chưa được cấu hình cho cuộc gọi nhóm")

    def room_name(self, call_id: int) -> str:
        return f"{self.settings.LIVEKIT_ROOM_PREFIX}{call_id}"

    def call_id(self, room_name: str):
        prefix = self.settings.LIVEKIT_ROOM_PREFIX
        suffix = room_name[len(prefix):] if room_name.startswith(prefix) else ""
        return int(suffix) if suffix.isdigit() else None

    def client(self):
        self.require_configured()
        return api.LiveKitAPI(
            self.settings.LIVEKIT_API_URL or self.settings.LIVEKIT_URL,
            self.settings.LIVEKIT_API_KEY, self.settings.LIVEKIT_API_SECRET,
            timeout=aiohttp.ClientTimeout(total=8),
        )

    def session(self, call_id: int, user_id: int, name: str) -> dict:
        self.require_configured()
        ttl = self.settings.LIVEKIT_TOKEN_TTL_SECONDS
        token = (api.AccessToken(self.settings.LIVEKIT_API_KEY, self.settings.LIVEKIT_API_SECRET)
                 .with_identity(f"user-{user_id}").with_name(name)
                 .with_ttl(timedelta(seconds=ttl))
                 .with_grants(api.VideoGrants(room_join=True, room=self.room_name(call_id),
                                              can_publish=True, can_subscribe=True, can_publish_data=False))
                 .to_jwt())
        return {"server_url": self.settings.LIVEKIT_URL, "participant_token": token,
                "call_id": call_id, "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl)}

    async def ensure_room(self, call_id: int):
        async with self.client() as client:
            await client.room.create_room(api.CreateRoomRequest(
                name=self.room_name(call_id), max_participants=self.settings.GROUP_CALL_MAX_PARTICIPANTS,
                empty_timeout=self.settings.GROUP_CALL_ADMISSION_SECONDS,
                departure_timeout=self.settings.GROUP_CALL_RECONNECT_SECONDS,
            ))

    async def participants(self, call_id: int) -> dict:
        async with self.client() as client:
            try:
                response = await client.room.list_participants(api.ListParticipantsRequest(room=self.room_name(call_id)))
            except api.TwirpError as exc:
                if exc.code == "not_found":
                    return {}
                raise
        return {p.identity: p for p in response.participants}

    async def remove(self, call_id: int, identity: str):
        async with self.client() as client:
            try:
                await client.room.remove_participant(api.RoomParticipantIdentity(
                    room=self.room_name(call_id), identity=identity,
                    # Cloud: không dùng cutoff mặc định có buffer một phút.
                    revoke_token_ts=int(time.time()) + 1 if self.settings.LIVEKIT_DEPLOYMENT == "cloud" else 0,
                ))
            except api.TwirpError as exc:
                if exc.code != "not_found":
                    raise

    async def delete_room(self, call_id: int):
        async with self.client() as client:
            try:
                await client.room.delete_room(api.DeleteRoomRequest(room=self.room_name(call_id)))
            except api.TwirpError as exc:
                if exc.code != "not_found":
                    raise

    def verify_webhook(self, body: str, authorization: str):
        receiver = api.WebhookReceiver(api.TokenVerifier(self.settings.LIVEKIT_API_KEY, self.settings.LIVEKIT_API_SECRET))
        return receiver.receive(body, authorization)

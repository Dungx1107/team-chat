"""Điều phối media SFU và nghiệp vụ; không dùng chat presence để tính người gọi."""
from asyncio import to_thread as run_in_threadpool


class GroupMediaService:
    def __init__(self, calls, gateway):
        self.calls = calls
        self.gateway = gateway

    async def session(self, call_id: int, user_id: int):
        self.gateway.require_configured()
        await run_in_threadpool(self.calls.require_sfu_admission, call_id, user_id)
        await self.gateway.ensure_room(call_id)
        # Kiểm tra lại sau I/O: user có thể đã bị xóa hoặc rời cuộc gọi.
        await run_in_threadpool(self.calls.require_sfu_admission, call_id, user_id)
        user = await run_in_threadpool(self.calls.user_repo.get_by_id, user_id)
        return self.gateway.session(call_id, user_id, user.full_name if user else f"User {user_id}")

    async def sync(self, call_id: int):
        remote = await self.gateway.participants(call_id)
        # Chỉ ACTIVE xác nhận media, JOINED của LiveKit mới là signaling.
        sessions = {int(identity[5:]): participant.sid for identity, participant in remote.items()
                    if identity.startswith("user-") and identity[5:].isdigit() and participant.state == 2}
        call = await run_in_threadpool(self.calls.sync_group_media, call_id, sessions)
        allowed = {f"user-{p.user_id}" for p in call.participants if p.is_active()} if call.is_open() else set()
        for identity in remote:
            if identity not in allowed:
                await self.gateway.remove(call_id, identity)
        if not call.is_open():
            await self.gateway.delete_room(call_id)
            if call.media_cleanup_pending:
                call.media_cleanup_pending = False
                call = await run_in_threadpool(self.calls.call_repo.save, call)
        return call

    async def leave(self, call_id: int, user_id: int):
        call = await run_in_threadpool(self.calls.leave_call, call_id, user_id)
        await self.gateway.remove(call_id, f"user-{user_id}")
        if not call.is_open():
            await self.gateway.delete_room(call_id)
            call.media_cleanup_pending = False
            await run_in_threadpool(self.calls.call_repo.save, call)
        return call

    async def remove_from_room(self, room_id: int, user_id: int):
        call = await run_in_threadpool(self.calls.call_repo.find_active_group_call, room_id)
        participant = call.get_participant(user_id) if call else None
        if participant and participant.is_active():
            await self.leave(call.id, user_id)

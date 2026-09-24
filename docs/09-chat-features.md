# 9. Chat features

## Room và member

`rooms.py` + `RoomService` xử lý tạo/list/update/delete, public/private room, avatar, join/leave và member role. `rooms.js` gọi API, giữ room cache và subscribe room hiện tại. Domain role là `OWNER`, `ADMIN`, `MEMBER`; service kiểm tra quyền trước thao tác quản trị.

Flow: `rooms.js -> rooms.py -> RoomService -> room_repo.py -> rooms/room_members -> event publisher -> ws.js/app.js`.

## Message

`messages.js` gửi text qua `POST /api/rooms/{room_id}/messages`, upload qua multipart endpoint, load history/pinned, edit/delete và render reply/forward metadata. `MessageService` kiểm tra room access, giới hạn content 4000 ký tự, persist qua `message_repo.py` và publish `message.created`, `updated`, `deleted`.

Xóa là soft delete. Attachment được liên kết optional với message; xem [11 - File storage](11-file-storage.md).

## Pin và reaction

Owner/admin có thể pin/unpin. Reaction toggle chỉ nhận tập emoji domain cho phép: `👍`, `❤️`, `😂`, `😮`, `😢`, `🎉`. Repository lưu unique theo message/user/emoji; event tương ứng là `message.pinned` và `message.reaction`.

## Typing/presence

`messages.js` gửi `typing.start/stop` qua `ws.js`; server broadcast trong subscription room. `app.js` cập nhật indicator và online state từ `user.online/offline`. Trạng thái không được lưu DB.

## Traceability

| Feature | Frontend | Backend |
| --- | --- | --- |
| Room | `rooms.js`, `app.js` | `routers/rooms.py`, `services/room_service.py`, `repositories/room_repo.py` |
| Message | `messages.js`, `ws.js` | `routers/messages.py`, `services/message_service.py`, `repositories/message_repo.py` |
| User/profile | `profile.js`, `api.js` | `routers/users.py`, `services/user_service.py`, `repositories/user_repo.py` |
| Realtime | `ws.js`, `app.js` | `routers/ws.py`, `infra/realtime/connection_manager.py` |

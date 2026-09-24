# 14. Code flow

## A. Login

```mermaid
sequenceDiagram
    participant F as api.js
    participant R as auth.py
    participant S as AuthService
    participant U as user_repo.py
    participant T as refresh_token_repo.py
    participant DB as PostgreSQL
    F->>R: POST /api/auth/login
    R->>S: login(LoginRequest)
    S->>U: find user
    S->>S: verify_password + create JWT
    S->>T: lưu hash refresh token
    T->>DB: insert
    S-->>F: TokenResponse
    F->>F: lưu localStorage
```

## B. Send message

```mermaid
sequenceDiagram
    participant F as messages.js/api.js
    participant R as messages.py
    participant S as MessageService
    participant M as message_repo.py
    participant DB as PostgreSQL
    participant W as event publisher/ConnectionManager
    participant C as other clients
    F->>R: POST /api/rooms/{id}/messages
    R->>S: create message
    S->>M: persist
    M->>DB: insert messages
    S->>W: message.created
    W-->>C: broadcast subscribed room
    R-->>F: message response
```

WebSocket không thay thế bước persistence; action `call.signal` là signaling riêng.

## C. Create room

`rooms.js -> POST /api/rooms -> rooms.py -> RoomService.create_room() -> room_repo.py -> rooms/room_members -> response + room event -> app.js cập nhật room list`. Owner được tạo cùng membership owner; private/public decision nằm trong request/schema/service.

## D. Upload file

`messages.js/profile.js/rooms.js -> multipart API -> router -> service -> LocalFileStorage.save() -> metadata/attachment repository hoặc avatar field -> uploads volume -> response`. Attachment download đi qua `GET /api/attachments/{attachment_id}` và kiểm tra quyền room.

## E. Call

`call.js -> POST /api/calls hoặc /api/calls/group -> CallService -> call_repo.py -> calls/call_participants -> call event qua ConnectionManager`. Sau đó `call.js` gửi `call.signal` (offer/answer/ice) qua `/ws`; backend relay signal, còn media chạy browser-to-browser WebRTC mesh.

## Traceability map

| Use case | Entry points | Core implementation |
| --- | --- | --- |
| Login/refresh | `frontend/js/api.js`, `auth.py` | `auth_service.py`, `jwt.py`, `password.py`, token repositories |
| Room/member | `frontend/js/rooms.js` | `rooms.py`, `room_service.py`, `room_repo.py` |
| Message | `frontend/js/messages.js` | `messages.py`, `message_service.py`, `message_repo.py` |
| Realtime | `frontend/js/ws.js` | `ws.py`, `connection_manager.py`, event publisher |
| Profile | `frontend/js/profile.js` | `users.py`, `user_service.py`, `user_repo.py` |
| Call | `frontend/js/call.js` | `calls.py`, `call_service.py`, `call_repo.py` |
| Files | `frontend/js/api.js` and feature modules | `file_storage.py`, `local_storage.py`, attachment/avatar routes |

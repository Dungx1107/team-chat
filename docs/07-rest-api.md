# 7. REST API

Router thực tế nằm trong `backend/app/api/routers/`. Trừ endpoint auth, health/docs và avatar public, endpoint nghiệp vụ yêu cầu `Authorization: Bearer <access_token>`.

## Auth - `auth.py`

| Method | Path | Chức năng |
| --- | --- | --- |
| POST | `/api/auth/register` | đăng ký |
| POST | `/api/auth/login` | đăng nhập/cấp token |
| POST | `/api/auth/refresh` | rotate refresh token |

## User - `users.py`

| Method | Path | Chức năng |
| --- | --- | --- |
| GET | `/api/users/me` | profile hiện tại |
| PATCH | `/api/users/me` | cập nhật profile |
| POST | `/api/users/me/avatar` | upload avatar |
| GET | `/api/users/search?q=...` | tìm user |
| GET | `/api/users/online` | user online |
| GET | `/api/users/{user_id}` | profile user |
| GET | `/api/users/{user_id}/avatar` | lấy avatar |

## Room/member - `rooms.py`

| Method | Path | Chức năng |
| --- | --- | --- |
| POST | `/api/rooms` | tạo room |
| GET | `/api/rooms` | list room |
| GET/PATCH/DELETE | `/api/rooms/{room_id}` | xem/sửa/xóa room |
| POST/GET | `/api/rooms/{room_id}/avatar` | upload/lấy avatar |
| GET | `/api/rooms/{room_id}/active-call` | call nhóm đang active |
| POST/DELETE | `/api/rooms/{room_id}/join` / `leave` | tham gia/rời |
| GET | `/api/rooms/{room_id}/members` | list member |
| POST | `/api/rooms/{room_id}/members` | add member |
| DELETE | `/api/rooms/{room_id}/members/{user_id}` | remove member |
| PATCH | `/api/rooms/{room_id}/members/{user_id}/role` | đổi role |

## Message - `messages.py`

| Method | Path | Chức năng |
| --- | --- | --- |
| POST | `/api/rooms/{room_id}/messages` | gửi text |
| POST | `/api/rooms/{room_id}/messages/upload` | gửi file message |
| GET | `/api/rooms/{room_id}/messages` | lịch sử |
| GET | `/api/rooms/{room_id}/pinned-messages` | tin đã pin |
| PATCH/DELETE | `/api/messages/{message_id}` | sửa/xóa mềm |
| POST/DELETE | `/api/messages/{message_id}/pin` | pin/unpin |
| POST | `/api/messages/{message_id}/reactions` | toggle reaction |
| GET | `/api/attachments/{attachment_id}` | download/stream |

## Call - `calls.py`

| Method | Path | Chức năng |
| --- | --- | --- |
| GET | `/api/calls/config` | config call/STUN |
| POST | `/api/calls` | start direct call |
| POST | `/api/calls/group` | start group call |
| GET | `/api/calls` / `/{call_id}` | list/get call |
| POST | `/api/calls/{call_id}/join` | join |
| POST | `/api/calls/{call_id}/leave` | leave |
| POST | `/api/calls/{call_id}/accept` | accept direct |
| POST | `/api/calls/{call_id}/decline` | decline |
| POST | `/api/calls/{call_id}/end` | end |

System routes: `GET /health`, `/docs`, `/redoc`, `/api/openapi.json`. Request/response fields chính được định nghĩa ở `backend/app/api/schemas/*.py`; router là nguồn chuẩn cho status và service call.

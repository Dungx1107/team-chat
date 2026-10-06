# 7. REST API

**52 endpoint** trong 5 router, cộng `/health` và kênh WebSocket `/ws`. Tài liệu tương tác
tự sinh có ở `https://localhost/docs` khi hệ thống đang chạy — đó là nguồn chính xác nhất
về kiểu dữ liệu từng trường.

## Quy ước chung

| Mục | Quy ước |
|---|---|
| Tiền tố | `/api` (riêng WebSocket là `/ws`) |
| Xác thực | `Authorization: Bearer <access_token>` cho mọi endpoint, trừ các endpoint đánh dấu 🔓 |
| Định dạng | JSON; riêng tải tệp dùng `multipart/form-data` |
| Thời gian | ISO 8601, giờ UTC, không có hậu tố múi giờ |
| Lỗi | `{"detail": "thông báo tiếng Việt"}` |

| Mã | Khi nào |
|---|---|
| `200` / `201` / `204` | Thành công / đã tạo / thành công không có nội dung |
| `400` | Dữ liệu sai nghiệp vụ (`ValueError` từ service) |
| `401` | Thiếu token, token sai, hết hạn |
| `403` | Không đủ quyền (`PermissionError`) |
| `404` | Không tìm thấy (`ValueError` ở các endpoint tra cứu) |
| `409` | Xung đột trạng thái — đang bận cuộc gọi khác (`RuntimeError`) |
| `422` | Sai định dạng — Pydantic từ chối trước khi vào service |

## Xác thực — `routers/auth.py`

| | Phương thức | Đường dẫn | Body | Trả về |
|---|---|---|---|---|
| 🔓 | POST | `/api/auth/register` | `email`, `username` (3–50), `password` (≥6), `first_name`, `last_name` | `201` thông tin người dùng (**không** có token) |
| 🔓 | POST | `/api/auth/login` | `email`, `password` | `access_token`, `refresh_token`, `token_type`, `user` |
| 🔓 | POST | `/api/auth/google` | `credential` (Google ID Token) | Như `/login` |
| 🔓 | POST | `/api/auth/refresh` | `refresh_token` | Cặp token mới. Token cũ bị thu hồi |

## Người dùng — `routers/users.py`

| | Phương thức | Đường dẫn | Ghi chú |
|---|---|---|---|
| | GET | `/api/users/me` | Hồ sơ đầy đủ của mình |
| | PATCH | `/api/users/me` | `first_name`, `last_name`, `bio` (≤500), `status` (≤100) — gửi trường nào sửa trường đó. Phát `user.updated` |
| | POST | `/api/users/me/avatar` | multipart `file`: JPEG/PNG/GIF/WEBP, ≤5 MB. Xóa ảnh cũ. Phát `user.updated` |
| | GET | `/api/users/search?q=&limit=20` | Khớp một phần với username, **email**, họ hoặc tên. Kết quả không chứa email, nhưng tìm theo email vẫn cho biết email đó có tài khoản hay không |
| | GET | `/api/users/online` | Danh sách `user_id` đang có kết nối WebSocket |
| | GET | `/api/users/{user_id}` | Hồ sơ công khai (không có email) |
| 🔓 GET | GET | `/api/users/{user_id}/avatar` | Ảnh đại diện. Công khai **chỉ với GET** để thẻ `<img>` dùng được |

## Phòng — `routers/rooms.py`

### Phòng

| Phương thức | Đường dẫn | Quyền | Ghi chú |
|---|---|---|---|
| POST | `/api/rooms` | đăng nhập | `name` (1–150), `description` (≤300), `is_private`, `theme_color` (`#rrggbb`). Người tạo thành OWNER |
| GET | `/api/rooms?limit=50&offset=0` | đăng nhập | **Chỉ phòng mình đã tham gia**, kèm `my_role`, `member_count`, `last_message`. Có trường `unread_count` nhưng server **luôn trả 0**; frontend tự đếm nhưng hiện gần như không bao giờ tăng — xem [08](08-websocket-realtime.md#client-chỉ-theo-dõi-một-phòng-tại-một-thời-điểm) |
| GET | `/api/rooms/search?q=&limit=20` | đăng nhập | Phòng **công khai** có tên chứa `q`, bỏ phòng mình bị chặn. `%` và `_` hiểu là ký tự thường |
| GET | `/api/rooms/{room_id}` | thành viên, hoặc người ngoài với phòng công khai (trừ người bị chặn) | |
| PATCH | `/api/rooms/{room_id}` | OWNER, ADMIN | `name`, `description`, `theme_color`. Phát `room.updated` |
| DELETE | `/api/rooms/{room_id}` | OWNER | `204`. Phát `room.deleted` |
| POST | `/api/rooms/{room_id}/avatar` | OWNER, ADMIN | multipart `file`, ảnh ≤5 MB. Phát `room.avatar_updated` |
| 🔓 GET | `/api/rooms/{room_id}/avatar` | công khai | Chỉ GET |
| GET | `/api/rooms/{room_id}/media` | như xem phòng | Danh sách tệp đã gửi trong phòng |
| GET | `/api/rooms/{room_id}/active-call` | thành viên | Cuộc gọi nhóm đang diễn ra, hoặc `null` |

⚠️ `/api/rooms/search` phải khai báo **trước** `/api/rooms/{room_id}` trong file, nếu không
FastAPI hiểu `search` là `room_id` và trả `422`.

### Thành viên

| Phương thức | Đường dẫn | Quyền | Ghi chú |
|---|---|---|---|
| POST | `/api/rooms/{room_id}/join` | đăng nhập | Phòng công khai. `403` nếu phòng riêng tư hoặc mình **bị chặn**. Phát `room.member_joined` |
| DELETE | `/api/rooms/{room_id}/leave` | ADMIN, MEMBER | OWNER không rời được. Phát `room.member_left` |
| GET | `/api/rooms/{room_id}/members` | như xem phòng | Kèm `role`, `nickname`, `is_online` |
| POST | `/api/rooms/{room_id}/members` | OWNER, ADMIN | `user_id`. Thêm thẳng không cần đồng ý. **Gỡ lệnh chặn** nếu có |
| DELETE | `/api/rooms/{room_id}/members/{user_id}` | OWNER, ADMIN (cao hơn người bị xóa) | `204`. **Ghi lệnh chặn**, thu hồi kênh realtime. Phát `room.member_left` |
| PATCH | `/api/rooms/{room_id}/members/{user_id}/role` | OWNER | `role`: `ADMIN` hoặc `MEMBER`. Phát `room.role_changed` |
| PATCH | `/api/rooms/{room_id}/members/{user_id}/nickname` | thành viên | `nickname` (≤100, rỗng để xóa). Tạo tin hệ thống. Phát `room.nickname_updated` |

### Lời mời

| Phương thức | Đường dẫn | Quyền | Ghi chú |
|---|---|---|---|
| POST | `/api/rooms/{room_id}/invites` | OWNER, ADMIN | `user_id`. Từ chối nếu đã là thành viên hoặc đang có lời mời chờ. Gửi `room.invite` tới người được mời |
| GET | `/api/rooms/notifications/invites` | đăng nhập | Lời mời đang chờ của mình |
| POST | `/api/rooms/notifications/invites/{invite_id}/accept` | người được mời | Vào phòng, **gỡ lệnh chặn**, tạo tin hệ thống. Phát `room.member_joined` |
| POST | `/api/rooms/notifications/invites/{invite_id}/reject` | người được mời | |

🐞 Chấp nhận lời mời **lần thứ hai** cho cùng người và phòng trả `500` — xem
[05](05-database.md#room_invites).

## Tin nhắn — `routers/messages.py`

| Phương thức | Đường dẫn | Quyền | Ghi chú |
|---|---|---|---|
| GET | `/api/rooms/{room_id}/messages?limit=50&offset=0` | thành viên | **50 tin mới nhất**, sắp xếp cũ → mới. `offset=50` là 50 tin cũ hơn nữa |
| POST | `/api/rooms/{room_id}/messages` | thành viên | `content` (1–4000), `reply_to_id`. Phát `message.created`, `room.summary_updated` |
| POST | `/api/rooms/{room_id}/messages/upload` | thành viên | multipart `file` (≤25 MB), `caption`. Phát như trên |
| GET | `/api/rooms/{room_id}/pinned-messages` | thành viên | Mới ghim nhất trước |
| PATCH | `/api/messages/{message_id}` | người gửi | `content`. Phát `message.updated` |
| DELETE | `/api/messages/{message_id}` | người gửi, hoặc OWNER/ADMIN | Xóa **mềm**. Phát `message.deleted` |
| POST | `/api/messages/{message_id}/pin` | OWNER, ADMIN | Phát `message.pinned` (`pinned: true`) |
| DELETE | `/api/messages/{message_id}/pin` | OWNER, ADMIN | Phát `message.pinned` (`pinned: false`) |
| POST | `/api/messages/{message_id}/reactions` | thành viên | `emoji`: một trong 👍 ❤️ 😂 😮 😢 🎉. Thả lần nữa là **gỡ**. Phát `message.reaction` |
| GET | `/api/attachments/{attachment_id}` | thành viên phòng chứa tệp | Tải tệp. Cần token, nên frontend tải bằng `fetch` rồi tạo `blob:` URL |

Gửi tin vào phòng mình **chưa tham gia** trả `403` — phải gọi `/join` trước.

## Cuộc gọi — `routers/calls.py`

| Phương thức | Đường dẫn | Quyền | Ghi chú |
|---|---|---|---|
| GET | `/api/calls/config` | đăng nhập | Danh sách máy chủ ICE (STUN/TURN) từ `ICE_SERVERS` |
| POST | `/api/calls` | thành viên phòng | Gọi 1-1: `callee_id`, `room_id`, `kind` (`AUDIO`/`VIDEO`). `409` nếu một trong hai đang bận. Gửi `call.incoming` tới người nhận |
| POST | `/api/calls/group` | thành viên phòng | `room_id`, `kind`. Phòng chưa có cuộc gọi nhóm thì mở mới và phát `call.room_started`; đã có thì **vào luôn cuộc đang diễn ra** |
| POST | `/api/calls/{call_id}/join` | thành viên phòng | Vào cuộc gọi nhóm. Tối đa 6 người |
| POST | `/api/calls/{call_id}/leave` | người trong cuộc gọi | Người cuối rời thì cuộc gọi kết thúc |
| POST | `/api/calls/{call_id}/accept` | người được gọi | Chỉ khi đang `RINGING` |
| POST | `/api/calls/{call_id}/decline` | người được gọi | → `REJECTED` |
| POST | `/api/calls/{call_id}/end` | người trong cuộc gọi | `missed` (tùy chọn). Đang đổ chuông → `CANCELED`/`MISSED`; đang nói → `ENDED` |
| GET | `/api/calls?limit=30` | đăng nhập | Lịch sử cuộc gọi của mình. Chưa có giao diện dùng |
| GET | `/api/calls/{call_id}` | người trong cuộc gọi | |

Tín hiệu WebRTC (offer/answer/ICE) **không** đi qua REST mà qua WebSocket — xem
[08](08-websocket-realtime.md#hành-động-client-gửi-lên).

## Khác

| | Phương thức | Đường dẫn | Ghi chú |
|---|---|---|---|
| 🔓 | GET | `/health` | `status`, `version`, `online_users`. Không có tiền tố `/api` |
| 🔓 | GET | `/docs`, `/redoc` | Tài liệu tương tác |
| 🔓 | GET | `/api/openapi.json` | Đặc tả OpenAPI |

## Thử nhanh bằng curl

```bash
# Đăng nhập — bằng email, không phải username
TOKEN=$(curl -sk -X POST https://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user1@example.com","password":"password123"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Phòng của tôi
curl -sk https://localhost/api/rooms -H "Authorization: Bearer $TOKEN"

# Tìm phòng công khai
curl -sk "https://localhost/api/rooms/search?q=kiến" -H "Authorization: Bearer $TOKEN"
```

`-k` bỏ qua cảnh báo chứng chỉ tự ký.

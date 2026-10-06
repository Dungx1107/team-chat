# Team Chat

Hệ thống chat nội bộ theo phòng, hỗ trợ xác thực người dùng, phân quyền thành viên, tin nhắn realtime qua WebSocket, tệp đính kèm, ảnh đại diện và reaction.

Tài liệu này mô tả kiến trúc, đặc tả kỹ thuật, giao diện API và quy trình triển khai của dự án.

## 1. Tổng quan

### 1.1. Mục tiêu

- Cung cấp không gian trao đổi theo phòng công khai hoặc riêng tư.
- Quản lý tài khoản, hồ sơ cá nhân và trạng thái online.
- Gửi tin nhắn văn bản, tệp đính kèm và biểu cảm.
- Cập nhật tin nhắn, thành viên và trạng thái typing theo thời gian thực.
- Tách biệt lớp API, nghiệp vụ, domain, persistence và hạ tầng để dễ bảo trì.

### 1.2. Phạm vi chức năng

| Nhóm | Chức năng |
| --- | --- |
| Tài khoản | Đăng ký, đăng nhập, làm mới phiên, quản lý hồ sơ và avatar |
| Phòng chat | Tạo, xem, cập nhật, xóa phòng; tham gia/rời phòng |
| Thành viên | Mời, xóa, xem danh sách và thay đổi vai trò thành viên |
| Tin nhắn | Gửi, đọc, xóa mềm tin nhắn văn bản hoặc tin nhắn có file |
| Realtime | Kết nối WebSocket, subscribe phòng, typing, cập nhật sự kiện |
| Tệp | Upload attachment, lưu persistent, tải/stream theo quyền truy cập |
| Phản ứng | Toggle reaction trên tin nhắn |

## 2. Kiến trúc hệ thống

Hệ thống gồm ba thành phần triển khai chính:

```mermaid
flowchart LR
    Browser[Trình duyệt]
    Web[Nginx\nHTTPS :443 / HTTP :80\nTunnel :8080]
    Backend[FastAPI + Uvicorn\nHTTP :8000\nWebSocket /ws]
    Database[(PostgreSQL 16)]
    Storage[(Docker volume\nuploads)]

    Browser --> Web
    Web -->|static frontend, /api, /ws| Backend
    Backend --> Database
    Backend --> Storage
```

### 2.1. Backend

Backend chạy bằng FastAPI và Uvicorn, được tổ chức theo các lớp:

```text
backend/app/
├── api/                 # Router, schema HTTP, middleware, dependency wiring
├── domain/              # Entity và interface nghiệp vụ
├── services/            # Use case và luật nghiệp vụ
├── repositories/        # Adapter truy cập dữ liệu qua SQLAlchemy
├── infra/
│   ├── db/              # Engine, session, ORM model
│   ├── realtime/        # ConnectionManager cho WebSocket
│   ├── security/        # JWT và hash mật khẩu
│   └── storage/         # Lưu file cục bộ
└── main.py              # Khởi tạo FastAPI và đăng ký router
```

Luồng xử lý HTTP tiêu chuẩn:

```text
Request
  -> Middleware xác thực
  -> Router
  -> Dependency injection
  -> Service
  -> Domain interface / Repository / Infrastructure adapter
  -> PostgreSQL hoặc file storage
  -> Response schema
```

Service không phụ thuộc trực tiếp vào FastAPI hoặc SQLAlchemy cho logic nghiệp vụ. Repository chịu trách nhiệm chuyển đổi giữa ORM model và domain model.

### 2.2. Frontend

Frontend là ứng dụng tĩnh, không dùng bundler hoặc framework JavaScript:

```text
frontend/
├── index.html       # Layout đăng nhập, chat, modal và các view chính
├── css/style.css    # CSS bổ sung
└── js/
    ├── api.js       # REST client, token, refresh, upload/download
    ├── app.js       # Vòng đời ứng dụng và điều phối sự kiện
    ├── messages.js  # Tin nhắn, file, reaction, typing
    ├── profile.js   # Hồ sơ người dùng và avatar
    ├── rooms.js     # Phòng và thành viên
    ├── ui.js        # Tiện ích giao diện
    └── ws.js        # WebSocket, reconnect và subscribe phòng
```

Frontend dùng Tailwind CDN trong `index.html` kết hợp với `frontend/css/style.css`. Frontend được Nginx phục vụ cùng origin với API và WebSocket:

```text
Giao diện: https://<hostname>/
REST:      https://<hostname>/api
WebSocket: wss://<hostname>/ws
```

Chạy HTTPS là cần thiết cho quyền microphone/camera của trình duyệt khi dùng
tính năng gọi. Backend vẫn lắng nghe nội bộ ở cổng `8000`; người dùng truy cập
qua Nginx, không truy cập trực tiếp frontend bằng Python HTTP Server.

### 2.3. Docker và triển khai

`docker-compose.yml` định nghĩa ba service chạy mặc định:

| Service | Công nghệ | Cổng | Persistent data |
| --- | --- | --- | --- |
| `db` | PostgreSQL 16 Alpine | Host `5432` -> container `5432` | Volume `pgdata` |
| `backend` | Python 3.11 + Uvicorn | Host `${PORT:-8000}` -> container `8000` | Volume `uploads` |
| `web` | Nginx Alpine | `${HTTPS_PORT:-443}`, `${HTTP_PORT:-80}`, tunnel `127.0.0.1:${TUNNEL_PORT:-8080}` | Volume `certs` |

Đặc điểm container backend:

- Chờ database đạt trạng thái healthy trước khi khởi động.
- Chạy bằng user non-root `appuser`.
- Mount mã nguồn `./backend:/app` trong môi trường phát triển.
- Lưu file tại `/app/uploads` và ánh xạ vào named volume `uploads`.
- Frontend được mount read-only vào Nginx và chạy cùng service `web`.
- Cổng `8080` chỉ bind trên localhost để dùng với Cloudflare Tunnel/ngrok.

## 3. Đặc tả giao diện

### 3.1. Địa chỉ dịch vụ

| Thành phần | URL mặc định | Mô tả |
| --- | --- | --- |
| Giao diện | `https://localhost` | Frontend qua Nginx |
| Backend API | `https://localhost/api` | REST API qua Nginx |
| Swagger UI | `https://localhost/docs` | Tài liệu API tương tác |
| ReDoc | `https://localhost/redoc` | Tài liệu API dạng ReDoc |
| OpenAPI | `https://localhost/api/openapi.json` | Đặc tả OpenAPI |
| Health check | `https://localhost/health` | Kiểm tra trạng thái backend |
| WebSocket | `wss://localhost/ws` | Kênh realtime |

### 3.2. REST API

Các endpoint nghiệp vụ đều nằm dưới prefix `/api`. Những endpoint cần xác thực nhận header:

```http
Authorization: Bearer <access_token>
```

#### Xác thực

| Method | Endpoint | Mô tả |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Tạo tài khoản |
| `POST` | `/api/auth/login` | Đăng nhập và cấp token |
| `POST` | `/api/auth/refresh` | Rotation refresh token |

#### Phòng và thành viên

| Method | Endpoint | Mô tả |
| --- | --- | --- |
| `POST` | `/api/rooms` | Tạo phòng |
| `GET` | `/api/rooms` | Liệt kê phòng được phép xem |
| `GET` | `/api/rooms/{room_id}` | Xem thông tin phòng |
| `PATCH` | `/api/rooms/{room_id}` | Cập nhật tên/mô tả |
| `DELETE` | `/api/rooms/{room_id}` | Xóa phòng |
| `POST` | `/api/rooms/{room_id}/join` | Tham gia phòng công khai |
| `DELETE` | `/api/rooms/{room_id}/leave` | Rời phòng |
| `GET` | `/api/rooms/{room_id}/members` | Liệt kê thành viên |
| `POST` | `/api/rooms/{room_id}/members` | Thêm thành viên trực tiếp |
| `POST` | `/api/rooms/{room_id}/invites` | Gửi lời mời chờ chấp nhận |
| `GET` | `/api/rooms/notifications/invites` | Lấy lời mời đang chờ |
| `POST` | `/api/rooms/notifications/invites/{invite_id}/accept` | Chấp nhận lời mời |
| `POST` | `/api/rooms/notifications/invites/{invite_id}/reject` | Từ chối lời mời |
| `DELETE` | `/api/rooms/{room_id}/members/{user_id}` | Xóa thành viên |
| `PATCH` | `/api/rooms/{room_id}/members/{user_id}/role` | Đổi vai trò |

Quyền thành viên theo thứ tự: `OWNER > ADMIN > MEMBER`. Phòng công khai có thể được tìm thấy bởi mọi user đã đăng nhập; phòng riêng chỉ hiển thị với thành viên. Khi có lời mời, server phát event WebSocket `room.invite`; khi người nhận chấp nhận, họ được thêm vào phòng và nhận tin nhắn hệ thống thông báo đã vào phòng.

#### Tin nhắn và file

| Method | Endpoint | Mô tả |
| --- | --- | --- |
| `POST` | `/api/rooms/{room_id}/messages` | Gửi tin nhắn văn bản |
| `POST` | `/api/rooms/{room_id}/messages/upload` | Gửi tin nhắn kèm file |
| `GET` | `/api/rooms/{room_id}/messages` | Lấy lịch sử tin nhắn |
| `PATCH` | `/api/messages/{message_id}` | Chỉnh sửa tin nhắn của mình |
| `DELETE` | `/api/messages/{message_id}` | Thu hồi tin nhắn |
| `POST` | `/api/messages/{message_id}/pin` | Ghim tin nhắn (OWNER/ADMIN) |
| `DELETE` | `/api/messages/{message_id}/pin` | Bỏ ghim tin nhắn (OWNER/ADMIN) |
| `POST` | `/api/messages/{message_id}/reactions` | Toggle reaction |
| `GET` | `/api/attachments/{attachment_id}` | Stream hoặc tải file |

Giới hạn nghiệp vụ chính:

- Nội dung tin nhắn tối đa 4000 ký tự.
- File đính kèm tối đa 25 MB.
- Reaction hợp lệ: `👍`, `❤️`, `😂`, `😮`, `😢`, `🎉`.
- File ảnh, video và audio được stream inline; loại file khác được tải xuống.

#### Người dùng

| Method | Endpoint | Mô tả |
| --- | --- | --- |
| `GET` | `/api/users/me` | Lấy hồ sơ hiện tại |
| `PATCH` | `/api/users/me` | Cập nhật hồ sơ |
| `POST` | `/api/users/me/avatar` | Upload avatar |
| `GET` | `/api/users/search?q=...` | Tìm người dùng |
| `GET` | `/api/users/online` | Danh sách user online |
| `GET` | `/api/users/{user_id}` | Xem hồ sơ người dùng |
| `GET` | `/api/users/{user_id}/avatar` | Lấy avatar |

Avatar chỉ nhận JPEG, PNG, GIF hoặc WEBP, tối đa 5 MB. Endpoint avatar được thiết kế public để trình duyệt có thể tải ảnh trực tiếp.

### 3.3. WebSocket protocol

Kết nối bằng access token trên query string:

```text
ws://<host>:8000/ws?token=<access_token>
```

Token nằm trên query string vì trình duyệt không cho tùy biến header `Authorization` khi khởi tạo WebSocket.

Các action client gửi:

```json
{"action":"subscribe","room_id":1}
{"action":"unsubscribe","room_id":1}
{"action":"typing.start","room_id":1}
{"action":"typing.stop","room_id":1}
{"action":"ping"}
```

Các event server phát:

- `connected`
- `message.created`
- `message.updated`, `message.deleted`, `message.reaction`, `message.pinned`
- `user.updated`, `user.online`, `user.offline`
- `typing.start`, `typing.stop`
- `room.member_joined`
- `room.member_left`
- `room.role_changed`
- `room.updated`
- `room.deleted`
- `room.invite`
- `error`

`ConnectionManager` lưu kết nối, subscription và trạng thái online trong memory của process backend hiện tại.

Khi thay đổi schema database trong Pha 1 (không dùng Alembic), reset volume rồi dựng lại:

```bash
docker compose down -v
docker compose up --build
```

## 4. Xác thực và bảo mật

### 4.1. Luồng xác thực

1. Đăng ký tạo user mới; mật khẩu được hash bằng Passlib/bcrypt.
2. Đăng nhập kiểm tra email và mật khẩu.
3. Backend cấp JWT access token và refresh token ngẫu nhiên.
4. Database chỉ lưu SHA-256 hash của refresh token.
5. Middleware xác thực access token và gắn `request.state.user_id`.
6. Frontend lưu access token, refresh token và user hiện tại trong `localStorage`.
7. Khi nhận HTTP `401`, frontend gọi `/api/auth/refresh`, cập nhật token và retry request một lần.
8. Refresh token được rotation và có thời hạn 7 ngày.

Access token hiện được tạo với thời hạn 60 phút trong `backend/app/infra/security/jwt.py`. Biến `ACCESS_TOKEN_EXPIRE_MINUTES` có trong cấu hình nhưng cần được kiểm tra nếu muốn dùng làm nguồn cấu hình thực tế.

### 4.2. Lưu trữ file

- `LocalFileStorage` lưu file trong `UPLOAD_DIR`.
- Tên vật lý trên đĩa được thay bằng UUID và giữ phần mở rộng.
- Có kiểm tra path traversal.
- Attachment lưu metadata trong database.
- Docker named volume `uploads` giúp dữ liệu file tồn tại qua lần recreate container.

## 5. Mô hình dữ liệu

```mermaid
erDiagram
    USERS ||--o{ REFRESH_TOKENS : owns
    USERS ||--o{ ROOMS : owns
    USERS ||--o{ ROOM_MEMBERS : joins
    ROOMS ||--o{ ROOM_MEMBERS : contains
    USERS ||--o{ MESSAGES : sends
    ROOMS ||--o{ MESSAGES : contains
    USERS ||--o{ ATTACHMENTS : uploads
    ATTACHMENTS ||--o{ MESSAGES : attaches
    MESSAGES ||--o{ REACTIONS : receives
    USERS ||--o{ REACTIONS : creates

    USERS {
        int id PK
        string email UK
        string username UK
        string password_hash
        string first_name
        string last_name
        boolean is_active
        string avatar_url
        string bio
        string status
        datetime created_at
    }
    ROOMS {
        int id PK
        string name
        string description
        boolean is_private
        int owner_id FK
        datetime created_at
    }
    ROOM_MEMBERS {
        int id PK
        int room_id FK
        int user_id FK
        string role
        datetime joined_at
    }
    MESSAGES {
        int id PK
        int room_id FK
        int user_id FK
        text content
        string message_type
        int attachment_id FK
        boolean is_deleted
        datetime edited_at
        datetime created_at
    }
```

Các bảng chính:

- `users`: tài khoản và hồ sơ cá nhân.
- `refresh_tokens`: refresh token đã hash, thời hạn và trạng thái thu hồi.
- `rooms`: thông tin phòng và chủ phòng.
- `room_members`: quan hệ nhiều-nhiều giữa user và room, kèm role.
- `messages`: nội dung tin nhắn, loại tin, trạng thái xóa mềm và attachment.
- `attachments`: metadata file và người upload.
- `reactions`: reaction theo user và emoji.

Ràng buộc đáng chú ý:

- Email và username là duy nhất.
- Một user chỉ có một membership trong một room.
- Một user chỉ thả một reaction cùng loại trên một message.
- Quan hệ user/room/message chính dùng `ON DELETE CASCADE`.
- Khi attachment bị xóa, `messages.attachment_id` được đặt thành `NULL`.
- Schema được tạo bằng `Base.metadata.create_all()`; dự án hiện chưa dùng migration framework.

## 6. Cấu hình môi trường

Tạo file `.env` từ `.env.example` và thay các giá trị bí mật trước khi triển khai.

| Biến | Mặc định/ý nghĩa |
| --- | --- |
| `PROJECT_NAME` | Tên API |
| `ENVIRONMENT` | Môi trường chạy |
| `PORT` | Cổng host map vào backend, mặc định `8000` |
| `POSTGRES_USER` | User PostgreSQL |
| `POSTGRES_PASSWORD` | Mật khẩu PostgreSQL |
| `POSTGRES_DB` | Tên database |
| `POSTGRES_HOST` | Host database |
| `POSTGRES_PORT` | Cổng database |
| `DATABASE_URL` | Chuỗi kết nối SQLAlchemy |
| `JWT_SECRET_KEY` | Secret ký JWT, phải đủ dài và bí mật |
| `JWT_ALGORITHM` | Thuật toán JWT, mặc định `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Cấu hình thời hạn access token |
| `UPLOAD_DIR` | Thư mục lưu file, mặc định `/app/uploads` |
| `MAX_UPLOAD_BYTES` | Kích thước upload tối đa, mặc định 25 MB |
| `CORS_ORIGINS` | Danh sách origin phân tách bằng dấu phẩy; `*` cho development |

Không commit `.env` hoặc secret thật vào repository.

## 7. Khởi động hệ thống

### 7.1. Điều kiện

- Docker Engine và Docker Compose.
- Cổng `80`, `443`, `5432` và `8000` không bị tiến trình khác chiếm.

### 7.2. Khởi động backend và database

```bash
docker compose up -d --build
docker compose ps
```

Mở giao diện tại `https://localhost`. Chứng chỉ local là self-signed; lần đầu
hãy chọn **Advanced → Proceed to localhost** trong trình duyệt.

Nạp dữ liệu mẫu:

```bash
docker compose exec backend python seed_users.py
```

`seed_users.py` tạo các tài khoản demo, phòng mẫu, membership và tin nhắn mẫu. Mật khẩu demo hiện là `password123`; chỉ dùng trong môi trường kiểm thử.

### 7.3. Tài khoản và phòng dùng để kiểm thử

`seed_users.py` tạo bốn tài khoản, tất cả dùng mật khẩu `password123`:

| Email | Username | Mục đích |
| --- | --- | --- |
| `user1@example.com` | `dungx` | chủ phòng |
| `user2@example.com` | `namtv` | ADMIN/thành viên |
| `user3@example.com` | `anhlh` | thành viên |
| `user4@example.com` | `maipt` | tài khoản chưa vào phòng, dùng để test lời mời |

### 7.4. Kiểm thử mời người dùng vào phòng

Mở hai cửa sổ trình duyệt, hoặc một cửa sổ thường và một cửa sổ ẩn danh:

1. Cửa sổ thứ nhất đăng nhập `user1@example.com`.
2. Tạo phòng riêng tư hoặc mở phòng có sẵn.
3. Mở bảng **👥 Thành viên**, bấm `+`, tìm `maipt` hoặc
   `user4@example.com`, rồi gửi lời mời.
4. Cửa sổ thứ hai đăng nhập `user4@example.com`.
5. Chuông `🔔` sẽ hiện thông báo lời mời theo thời gian thực.
6. Bấm **Nhận** để tham gia hoặc **Từ chối** để bỏ qua.

Khi chấp nhận, User 4 được thêm làm thành viên, phòng xuất hiện trong danh
sách của User 4 và khung chat hiển thị tin nhắn hệ thống dạng:

```text
Phương Mai đã vào phòng
```

Lời mời được lưu lại nên nếu người nhận offline, họ vẫn thấy lời mời sau khi
đăng nhập. Chi tiết API xem tại [docs/07-rest-api.md](docs/07-rest-api.md).

### 7.5. Truy cập từ mạng khác

Để chia sẻ ứng dụng qua Internet mà không mở port router:

```bash
cloudflared tunnel --url http://localhost:8080
```

Gửi URL `https://*.trycloudflare.com` cho người dùng khác. Giữ tiến trình
`cloudflared` chạy trong suốt thời gian sử dụng. Cloudflare Tunnel chuyển tiếp
website/API/WebSocket; cuộc gọi WebRTC có thể cần cấu hình TURN trong `.env`.
Xem hướng dẫn đầy đủ tại
[docs/16-goi-xuyen-mang-lam-may-chu.md](docs/16-goi-xuyen-mang-lam-may-chu.md).

Nếu gặp `Address already in use`, kiểm tra tiến trình đang chiếm cổng:

```bash
ss -ltnp | grep -E ':(80|443|5432|8000)'
kill <PID>
```

### 7.4. Dừng hoặc reset dữ liệu

```bash
# Dừng container, giữ nguyên volume
docker compose down

# Xóa cả volume database và upload; dữ liệu sẽ mất
docker compose down -v
```

## 8. Cây thư mục rút gọn

```text
team-chat/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── domain/
│   │   ├── infra/
│   │   ├── repositories/
│   │   ├── services/
│   │   └── main.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── seed_users.py
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/
├── docker-compose.yml
├── .env.example
├── RUN_GUIDE.md
└── README.md
```

## 9. Giới hạn và lưu ý triển khai

- CORS mặc định là `*`, phù hợp development nhưng cần giới hạn origin khi production.
- Frontend hiện dùng `http://` và `ws://`; khi triển khai HTTPS cần reverse proxy và `https://`/`wss://` tương ứng.
- Presence và WebSocket chỉ lưu trong memory của một backend process; chưa có Redis Pub/Sub, vì vậy chưa phù hợp scale ngang nhiều instance.
- Chưa có migration framework. Thay đổi schema cần có quy trình migration riêng hoặc reset database trong development.
- Backend container map cổng host theo `PORT`, trong khi Uvicorn bên trong container vẫn lắng nghe cổng `8000`.
- Attachment cần Bearer token khi truy cập. Quyền truy cập attachment nên được rà soát thêm nếu triển khai production nhiều tenant/phòng.
- Secret JWT, mật khẩu PostgreSQL và tài khoản demo phải được thay đổi trong môi trường thật.

## 10. Tài liệu liên quan

- [Hướng dẫn vận hành chi tiết](RUN_GUIDE.md)
- [Cấu hình mẫu](.env.example)
- [Docker Compose](docker-compose.yml)
- [Backend entrypoint](backend/app/main.py)
- [Database models](backend/app/infra/db/models.py)

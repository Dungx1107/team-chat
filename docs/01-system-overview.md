# 1. Tổng quan hệ thống

## Bối cảnh

Team Chat là đồ án môn Kiến trúc phần mềm. Pha 1 dựng hệ thống nền với đủ tính năng;
pha 2 cải tiến kiến trúc và đo hiệu năng trước/sau. Vì vậy code được tổ chức để **thay
được hạ tầng mà không sửa nghiệp vụ** — xem [02 - Kiến trúc](02-architecture.md).

## Các thành phần chạy

- **User/browser**: render `frontend/index.html`, gọi REST, duy trì WebSocket và thực hiện WebRTC ở client.
- **Nginx (`web`)**: terminate HTTPS, phục vụ frontend tĩnh, proxy `/api`, `/ws`, `/docs`, `/redoc`, `/health`.
- **FastAPI (`backend`)**: xác thực, use case, REST, WebSocket, signaling và truy cập persistence.
- **Supabase PostgreSQL**: dữ liệu user, room, message, call, token và metadata file; backend kết nối qua `DATABASE_URL` (Supavisor/Pooler).
- **Supabase Storage**: file đính kèm và ảnh đại diện trong bucket được cấu hình bởi `SUPABASE_STORAGE_BUCKET`.
- **STUN/TURN**: STUN mặc định giúp tìm đường kết nối; TURN bên ngoài hoặc service `turn` tùy chọn chuyển tiếp media khi WebRTC không thể kết nối trực tiếp.

| Container | Image | Vai trò | Cổng |
|---|---|---|---|
| `web` | nginx (build từ `deploy/nginx/`) | Kết thúc TLS, phục vụ `frontend/`, chuyển `/api` và `/ws` về backend | 443, 80, 127.0.0.1:8080 |
| `backend` | Python 3.11 (build từ `backend/`) | FastAPI: REST, WebSocket, nghiệp vụ | 8000 |
| `db` | `postgres:16-alpine` | Lưu toàn bộ dữ liệu có cấu trúc | 5432 |
| `turn` | `coturn/coturn` | Máy chủ TURN để thử gọi giữa hai mạng | 3478 — **chỉ chạy khi bật profile `turn`** |

Ngoài ra có hai thứ nằm **ngoài** hệ thống nhưng hệ thống phụ thuộc vào khi gọi qua Internet:
dịch vụ TURN bên ngoài (Metered) và Cloudflare Tunnel. Xem [15](15-third-party-services.md).

## Ba kênh giao tiếp

Đây là điều quan trọng nhất cần nắm: dữ liệu đi theo **ba đường khác nhau**, mỗi đường
hợp với một loại việc.

```mermaid
sequenceDiagram
    participant U as Browser
    participant N as Nginx
    participant A as FastAPI
    participant D as Supabase PostgreSQL
    participant F as Supabase Storage
    U->>N: HTTPS GET frontend / REST / WebSocket upgrade
    N->>A: proxy /api, /ws, /docs, /health
    A->>D: SQLAlchemy session qua DATABASE_URL
    A->>F: upload/download attachment hoặc avatar
    A-->>N: response/event
    N-->>U: HTTPS response or WebSocket event
    U<<->>S: WebRTC media (direct hoặc qua TURN)
```

| Kênh | Dùng cho | Vì sao chọn kênh này |
|---|---|---|
| **REST** (`/api/...`) | Mọi thao tác thay đổi dữ liệu: gửi tin, tạo phòng, đăng nhập | Có mã trạng thái rõ ràng, dễ kiểm tra quyền, dễ đo hiệu năng |
| **WebSocket** (`/ws`) | Server báo cho client: tin mới, ai đang gõ, ai vào phòng; chuyển tín hiệu bắt tay cuộc gọi | Server cần chủ động đẩy; trước đây client hỏi lại mỗi 2 giây |
| **WebRTC** | Âm thanh và hình ảnh cuộc gọi | Đi thẳng giữa hai trình duyệt, độ trễ thấp, máy chủ không phải gánh băng thông |

Một quy ước xuyên suốt: **ghi qua REST, nhận thay đổi qua WebSocket**. Ví dụ gửi tin:
client gọi `POST /api/rooms/{id}/messages`, và tất cả thành viên (kể cả người gửi) nhận
tin mới qua sự kiện `message.created`. WebSocket gần như không dùng để ghi dữ liệu — ngoại
lệ duy nhất là tín hiệu WebRTC (`call.signal`), vì ICE candidate sinh ra liên tục thành nhiều
gói nhỏ.

## Công nghệ

| Lớp | Công nghệ | Ghi chú |
|---|---|---|
| Ngôn ngữ backend | Python 3.11 | |
| Framework | FastAPI trên Starlette | Starlette cho phép REST và WebSocket chạy chung một tiến trình |
| Máy chủ ứng dụng | Uvicorn (ASGI) | **Một worker** — xem giới hạn ở [02](02-architecture.md#giới-hạn-khi-mở-rộng) |
| Kiểm tra dữ liệu | Pydantic v2, pydantic-settings | Schema vào/ra, đọc `.env` |
| ORM | SQLAlchemy 2.x (đồng bộ) | Chỉ xuất hiện ở tầng repository và infra |
| Driver | psycopg 3 | |
| CSDL | PostgreSQL 16 | |
| Bảo mật | PyJWT, passlib + bcrypt, google-auth | |
| Frontend | HTML + JavaScript thuần, Tailwind CSS qua CDN | Không có bước build |
| Gọi | WebRTC của trình duyệt, mô hình mesh | |
| Hạ tầng | Docker Compose, nginx, OpenSSL, coturn | |

Chi tiết từng thư viện backend làm gì: [03 - Backend](03-backend.md#thư-viện).

## Phạm vi tính năng

**Tài khoản:** đăng ký, đăng nhập bằng email + mật khẩu, đăng nhập bằng Google, làm mới
phiên, hồ sơ (họ tên, trạng thái, giới thiệu), ảnh đại diện, tìm người dùng.

**Phòng:** phòng công khai và riêng tư; phòng công khai **chỉ hiện khi tìm theo tên hoặc đã
tham gia**; ba vai trò OWNER > ADMIN > MEMBER; thêm, xóa, đổi vai trò thành viên; người bị
xóa **không tự vào lại được**; lời mời có chấp nhận/từ chối; biệt danh trong phòng; màu chủ
đề và ảnh đại diện phòng; thư viện tệp của phòng.

**Tin nhắn:** văn bản, tệp đính kèm (ảnh, video, âm thanh, tài liệu đến 25 MB), sửa, xóa
mềm, ghim, sáu loại biểu cảm, tin nhắn hệ thống, đang gõ, trạng thái online. Trả lời tin
mới có ở backend, giao diện chưa dùng.

**Cuộc gọi:** thoại hoặc video; 1-1 có đổ chuông; nhóm trong phòng tối đa 6 người; đi
thẳng hoặc qua TURN; chế độ `?relay=1` để kiểm tra TURN.

Mô tả hành vi chi tiết: [09](09-chat-features.md) và [10](10-call-features.md).

## Một request đi qua những đâu

Ví dụ: người dùng gửi tin "chào" vào phòng 1.

```mermaid
sequenceDiagram
    participant C1 as Client A
    participant WS as /ws + ConnectionManager
    participant S as Service
    participant DB as Supabase PostgreSQL
    participant C2 as Client B
    C1->>WS: action subscribe / typing / call.signal
    WS->>S: kiểm tra user/room hoặc chuyển signaling
    S->>DB: ghi dữ liệu nếu là use case bền vững
    S->>WS: publish event
    WS-->>C1: event
    WS-->>C2: event tới socket đã subscribe
```

`ConnectionManager` giữ socket, subscription, online và typing trong memory của một process. Vì vậy realtime không tự đồng bộ giữa nhiều backend process.

## Phạm vi đã xác định

Có authentication, refresh token, profile/avatar, room/member role, message CRUD mềm, attachment, reaction, pin, presence/typing và calls. Call dùng WebRTC mesh ở browser; backend chỉ lưu lifecycle và làm signaling, không vận chuyển media. Có STUN mặc định và hỗ trợ TURN bên ngoài hoặc coturn qua Compose profile `turn`; không có SFU, Redis/PubSub hay migration framework. PostgreSQL và object storage được cung cấp bởi Supabase, không chạy local trong Compose.

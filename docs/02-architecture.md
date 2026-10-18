# 2. Kiến trúc

Backend là một **khối nguyên (monolith) phân tầng** theo tinh thần Clean Architecture:
nghiệp vụ nằm ở giữa và không phụ thuộc vào bất kỳ công nghệ nào; công nghệ (web, ORM,
WebSocket, ổ đĩa) nằm ở vòng ngoài và phụ thuộc ngược vào nghiệp vụ qua các interface.

## Bốn tầng

```text
Browser
  -> Nginx (static frontend, TLS termination, reverse proxy)
  -> FastAPI/Uvicorn
  -> AuthenticationMiddleware / router
  -> Pydantic schema + dependency wiring
  -> Service (backend/app/services)
  -> Domain interface (backend/app/domain/interfaces)
  -> Repository implementation (backend/repositories)
  -> SQLAlchemy session/model (backend/app/infra/db)
  -> Supabase PostgreSQL qua `DATABASE_URL`
```

Upload đi theo nhánh `Service -> FileStorage interface -> SupabaseFileStorage -> Supabase Storage bucket`; realtime đi theo nhánh publisher/`ConnectionManager`.
Cuộc gọi tách thành hai mặt phẳng: signaling và lifecycle đi qua FastAPI/WebSocket/`CallService`, còn audio/video đi trực tiếp giữa các browser theo WebRTC mesh hoặc qua STUN/TURN khi cần.

### Đã kiểm chứng bằng `grep`

Đây không chỉ là ý định — có thể kiểm tra trên code hiện tại:

```bash
# domain/ chỉ import thư viện chuẩn và chính nó
grep -rhoE "^(from|import) [a-z_.]+" backend/app/domain/ | sort -u
# -> abc, datetime, typing, app.domain.*

`get_db()` tạo synchronous SQLAlchemy session từ `backend/app/infra/db/session.py`, kết nối tới Supabase PostgreSQL bằng `DATABASE_URL`. Các dependency trong `api/dependencies.py` dựng `UserRepository`, `RoomRepository`, `MessageRepository`, `CallRepository`, `RefreshTokenRepository`, `SupabaseFileStorage` và service tương ứng. Router nhận các đối tượng này qua `Depends` thay vì tự viết query. WebSocket tạo session riêng cho các thao tác kiểm tra room và signaling call, rồi đóng session sau mỗi thao tác.

Những chỗ hiện **chưa** theo đúng kiến trúc trên. Ghi ra để không ai tưởng là thiết kế
có chủ đích, và để làm cải tiến pha 2.

| # | Chỗ | Vấn đề | Hướng sửa |
|---|---|---|---|
| 1 | Lời mời thành viên (`routers/rooms.py`: `invite_member`, `accept_invite`, `reject_invite`, `list_invites`) | Toàn bộ nghiệp vụ nằm trong router; `InviteRepository` không có interface, trả thẳng `RoomInviteModel` của SQLAlchemy lên router; router tự gọi `connection_manager` thay vì qua `IEventPublisher` | Thêm thực thể `RoomInvite`, cổng `IInviteRepository`, chuyển logic vào `RoomService` |
| 2 | Biệt danh (`update_member_nickname`) và thư viện tệp (`list_room_media`) | Logic trong router, gọi thẳng `room_service.room_repo` | Chuyển thành phương thức của `RoomService` |
| 3 | Nhiều endpoint phòng đọc `room_service.room_repo` để lấy vai trò, đếm thành viên | Router với tay xuyên qua service xuống repository | Service trả về một đối tượng tổng hợp |
| 4 | `ws.py` tự tạo `RoomRepository` để kiểm tra quyền theo dõi phòng | Kiểm tra quyền nằm ngoài service | Gọi `RoomService.require_membership` |
| 5 | `main.py` chạy `ALTER TABLE` thô khi khởi động | Thay đổi schema không có phiên bản, không lùi lại được, nằm ngoài mọi tầng | Alembic |
| 6 | `AuthService` import thẳng `infra.security` và `google.oauth2` | Service phụ thuộc cài đặt cụ thể | Thêm cổng cho băm mật khẩu, cấp token, xác minh Google |
| 7 | Không có kiểm thử tự động | `NullEventPublisher` đã sẵn sàng nhưng chưa được dùng | `pytest` cho tầng service với repository giả |

## Giới hạn khi mở rộng

| Giới hạn | Nguyên nhân | Ảnh hưởng | Hướng cải tiến |
|---|---|---|---|
| Chỉ chạy được **một** tiến trình backend | `ConnectionManager` giữ kết nối và đăng ký phòng trong bộ nhớ | Chạy 2 worker là người ở worker 1 không nhận sự kiện từ worker 2 | Bộ chuyển đổi Redis Pub/Sub cho `IEventPublisher` |
| Gọi nhóm tối đa 6 người | Mesh: mỗi máy tải lên n−1 luồng | Máy yếu hoặc mạng upload kém sẽ giật | SFU (mediasoup, LiveKit) |
| Tệp nằm trên ổ đĩa một máy | `LocalFileStorage` | Không chia sẻ được giữa nhiều máy chủ | Bộ chuyển đổi S3/MinIO cho `IFileStorage` |
| Truy vấn danh sách phòng N+1 | Router gọi `get_member`, `count_members`, `get_last_message_summary` cho từng phòng | Chậm khi người dùng ở nhiều phòng | Một truy vấn gộp trong repository |

- `backend` và `web` là hai service Compose chạy mặc định; `turn` là service tùy chọn, bật bằng `docker compose --profile turn up -d`. Database và file storage nằm trên Supabase.
- Presence, subscription, typing và các event realtime nằm trong memory của một process backend. Không có broker nên không thể mở rộng ngang mà vẫn giữ trạng thái realtime nhất quán.
- Startup gọi `Base.metadata.create_all()`; chưa có migration có version.
- Nginx là cổng vào duy nhất trong topology chuẩn: phục vụ static frontend, terminate TLS và proxy REST/WebSocket. Backend không tự phục vụ frontend.

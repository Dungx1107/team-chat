# 2. Kiến trúc phần mềm

## Kiến trúc thực tế

Code thể hiện layered architecture kết hợp Service Layer, Repository Pattern và một mức interface/implementation separation. Đây không phải Clean Architecture thuần: `backend/app/api/dependencies.py` trực tiếp khởi tạo SQLAlchemy repositories và service; các router cũng biết một số infrastructure adapter.

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
  -> PostgreSQL
```

Upload đi theo nhánh `Service -> FileStorage interface -> LocalFileStorage -> filesystem`; realtime đi theo nhánh publisher/`ConnectionManager`.
Cuộc gọi tách thành hai mặt phẳng: signaling và lifecycle đi qua FastAPI/WebSocket/`CallService`, còn audio/video đi trực tiếp giữa các browser theo WebRTC mesh hoặc qua STUN/TURN khi cần.

## Trách nhiệm

| Layer | Vị trí | Trách nhiệm |
| --- | --- | --- |
| API | `backend/app/api/routers` | HTTP/WebSocket endpoint, status code, gọi service |
| Schema | `backend/app/api/schemas` | DTO request/response và validation Pydantic |
| Middleware/dependency | `api/middlewares`, `api/dependencies.py` | bearer auth, tạo session/repository/service |
| Domain | `backend/app/domain/models` | entity, enum, luật/constant domain |
| Domain interfaces | `backend/app/domain/interfaces` | contract cho repository, storage, event publisher |
| Service | `backend/app/services` | use case, authorization nghiệp vụ, phối hợp repo/event/storage |
| Repository | `backend/repositories` | SQLAlchemy query, mapping ORM <-> domain |
| Infrastructure | `backend/app/infra` | DB engine/session/model, JWT/hash, storage, realtime |

## Dependency injection

`get_db()` tạo synchronous SQLAlchemy session từ `backend/app/infra/db/session.py`. Các dependency trong `api/dependencies.py` dựng `UserRepository`, `RoomRepository`, `MessageRepository`, `CallRepository`, `RefreshTokenRepository`, `LocalFileStorage` và service tương ứng. Router nhận các đối tượng này qua `Depends` thay vì tự viết query. WebSocket tạo session riêng cho các thao tác kiểm tra room và signaling call, rồi đóng session sau mỗi thao tác.

## Pattern thể hiện trong code

- **Service Layer**: `AuthService`, `RoomService`, `MessageService`, `CallService`, `UserService` gom use case.
- **Repository Pattern**: interface trong `domain/interfaces/*_repo.py`, implementation cùng tên trong `backend/repositories/`.
- **DTO/Schema**: Pydantic schemas tách request/response khỏi domain entity.
- **Middleware**: `AuthenticationMiddleware` đặt `request.state.user_id` cho HTTP request.
- **Observer/event publisher**: `IEventPublisher` và `ConnectionManager` phát event tới client; publisher hỗ trợ gọi từ service đồng bộ bằng cách đưa coroutine vào event loop chính.
- **Separation of concerns**: persistence, security, storage và realtime nằm ở infrastructure.

Các interface không loại bỏ hoàn toàn coupling: repository implementation vẫn dùng trực tiếp SQLAlchemy và wiring tập trung ở API layer.

## Ranh giới triển khai

- `db`, `backend` và `web` là ba service Compose chạy mặc định; `turn` là service tùy chọn, bật bằng `docker compose --profile turn up -d`.
- Presence, subscription, typing và các event realtime nằm trong memory của một process backend. Không có broker nên không thể mở rộng ngang mà vẫn giữ trạng thái realtime nhất quán.
- Startup gọi `Base.metadata.create_all()`; chưa có migration có version.
- Nginx là cổng vào duy nhất trong topology chuẩn: phục vụ static frontend, terminate TLS và proxy REST/WebSocket. Backend không tự phục vụ frontend.

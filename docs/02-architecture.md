# 2. Kiến trúc phần mềm

## Kiến trúc thực tế

Code thể hiện layered architecture kết hợp Service Layer, Repository Pattern và một mức interface/implementation separation. Đây không phải Clean Architecture thuần: `backend/app/api/dependencies.py` trực tiếp khởi tạo SQLAlchemy repositories và service; các router cũng biết một số infrastructure adapter.

```text
Client
  -> AuthenticationMiddleware
  -> Router (backend/app/api/routers)
  -> Pydantic schema / dependency wiring
  -> Service (backend/app/services)
  -> Domain interface (backend/app/domain/interfaces)
  -> Repository implementation (backend/repositories)
  -> SQLAlchemy session/model (backend/app/infra/db)
  -> PostgreSQL
```

Upload đi theo nhánh `Service -> FileStorage interface -> LocalFileStorage -> filesystem`; realtime đi theo nhánh publisher/`ConnectionManager`.

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

`get_db()` tạo session từ `backend/app/infra/db/session.py`. Các dependency trong `api/dependencies.py` dựng `UserRepository`, `RoomRepository`, `MessageRepository`, `CallRepository`, `RefreshTokenRepository`, `LocalFileStorage` và service tương ứng. Router nhận các đối tượng này qua `Depends` thay vì tự viết query.

## Pattern thể hiện trong code

- **Service Layer**: `AuthService`, `RoomService`, `MessageService`, `CallService`, `UserService` gom use case.
- **Repository Pattern**: interface trong `domain/interfaces/*_repo.py`, implementation cùng tên trong `backend/repositories/`.
- **DTO/Schema**: Pydantic schemas tách request/response khỏi domain entity.
- **Middleware**: `AuthenticationMiddleware` đặt `request.state.user_id` cho HTTP request.
- **Observer/event publisher**: event publisher và `ConnectionManager` phát event tới client.
- **Separation of concerns**: persistence, security, storage và realtime nằm ở infrastructure.

Các interface không loại bỏ hoàn toàn coupling: repository implementation vẫn dùng trực tiếp SQLAlchemy và wiring tập trung ở API layer.

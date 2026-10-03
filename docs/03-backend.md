# 3. Backend

## Runtime và thư viện

Backend chạy Python 3.11, FastAPI và Uvicorn. Pydantic/Pydantic Settings xử lý schema/config; SQLAlchemy 2.x synchronous ORM và `psycopg[binary]` (psycopg 3) kết nối PostgreSQL; PyJWT tạo/giải JWT; Passlib/bcrypt hash password; `python-multipart` xử lý upload; `websockets` hỗ trợ client/server WebSocket.

Dependencies nằm trong `backend/requirements.txt`. Entrypoint là `backend/app/main.py`: tạo app, gọi `Base.metadata.create_all()`, đăng ký middleware/router và expose health/docs.

## Router

`auth.py`, `users.py`, `rooms.py`, `messages.py`, `calls.py` đăng ký dưới prefix `/api`; `ws.py` expose `/ws`. Router nhận schema và service qua dependency, không trực tiếp chứa toàn bộ query. Chi tiết endpoint ở [07 - REST API](07-rest-api.md).

## Service và repository

Service kiểm tra membership/role, tạo entity, gọi repository, commit dữ liệu và publish event. Repository ánh xạ domain model với ORM trong `backend/app/infra/db/models.py`. `session.py` cấu hình engine/session đồng bộ.

## Infrastructure

- `infra/security/jwt.py`, `password.py`: token và password.
- `infra/storage/local_storage.py`: file local với tên UUID.
- `infra/realtime/connection_manager.py`: socket/subscription/presence/typing in-memory và event publisher.
- `infra/db/models.py`, `session.py`: persistence.

Không có background worker hoặc async database layer được xác định từ source. Migration schema cũng không có; startup chỉ `create_all()`.

WebSocket server nhận heartbeat `ping` từ client mỗi 30 giây. Nếu quá `WS_IDLE_TIMEOUT_SECONDS` (mặc định 90 giây) không nhận được dữ liệu, server đóng socket bằng mã `4002`, giải phóng presence và kết thúc các cuộc gọi còn dang dở của user nếu đó là kết nối cuối cùng. Client tự kết nối lại; mã `4001` dành cho token không hợp lệ.

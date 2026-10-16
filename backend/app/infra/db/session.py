from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# # create_engine chính là nơi tạo ra Engine và Connection Pool
# engine = create_engine(
#     settings.DATABASE_URL,
#     pool_size=10,         # Số lượng kết nối duy trì thường trực trong bể
#     max_overflow=20,      # Số kết nối tối đa cho phép mở thêm nếu tải đột biến
#     pool_pre_ping=True,   # Tự động "ping" kiểm tra kết nối còn sống trước khi dùng
#     pool_recycle=3600,    # Tái tạo kết nối sau 1 giờ để tránh bị treo
# )
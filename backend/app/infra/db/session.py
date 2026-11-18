from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=settings.DB_POOL_SIZE,        # mặc định 20/worker (4 workers = 80)
    max_overflow=settings.DB_MAX_OVERFLOW,  # mặc định thêm 30/worker khi cao điểm (4 workers = 120)
    pool_timeout=30,       # Thời gian tối đa chờ lấy kết nối từ pool
    pool_pre_ping=True,    # Kiểm tra kết nối còn sống trước khi dùng
    pool_recycle=3600,     # Tái tạo kết nối sau 1 giờ
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


from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Team Chat API"
    DATABASE_URL: str = "postgresql://postgres:postgres_password@db:5432/teamchat_db"
    JWT_SECRET_KEY: str = "super-secret-key-change-it-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Nơi lưu tệp đính kèm và ảnh đại diện (gắn Docker volume)
    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024

    # Danh sách origin được phép gọi API; "*" chỉ dùng khi phát triển
    CORS_ORIGINS: str = "*"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def cors_origin_list(self) -> list:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

settings = Settings()

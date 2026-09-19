from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Team Chat API"
    DATABASE_URL: str = "postgresql://postgres:postgres_password@db:5432/teamchat_db"
    JWT_SECRET_KEY: str = "super-secret-key-change-it-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

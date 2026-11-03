import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
import jwt
from sqlalchemy import create_engine, text

# 1. Xác định đường dẫn file .env
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / "backend" / ".env"
if not ENV_PATH.exists():
    ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback_secret_key_for_dev")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
NUM_USERS = 2000

# Cấu hình kết nối Postgres Docker local
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/teamchat_db"
OUTPUT_CSV = Path(__file__).resolve().parent / "data" / "tokens.csv"


def seed_database_and_tokens():
    print(f"-> Kết nối tới Database local: {DATABASE_URL}")
    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        # Bổ sung cột hashed_password nếu chưa có
        conn.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_password VARCHAR(255);
        """))

        # 1. Nạp 500 Users vào Database local
        print(f"-> Đang nạp {NUM_USERS} Users vào Database local...")
        for user_id in range(1, NUM_USERS + 1):
            conn.execute(
                text("""
                    INSERT INTO users (id, email, username, first_name, last_name, hashed_password, is_active, created_at)
                    VALUES (:id, :email, :username, :first_name, :last_name, 'dummy_hash_for_test', true, NOW())
                    ON CONFLICT (id) DO NOTHING;
                """),
                {
                    "id": user_id,
                    "email": f"user{user_id}@benchmark.com",
                    "username": f"user_{user_id}",
                    "first_name": f"User",
                    "last_name": f"{user_id}"
                }
            )

        # 2. Tạo Room ID = 1 với owner_id = 1
        conn.execute(text("""
            INSERT INTO rooms (id, name, owner_id, is_private, created_at)
            VALUES (1, 'Benchmark Room', 1, false, NOW())
            ON CONFLICT (id) DO NOTHING;
        """))
        print("-> Đã khởi tạo Room ID = 1 (Owner: User 1).")

        # 3. Thêm 500 Users vào Room 1
        print("-> Đang gán 500 Users vào Room 1...")
        for user_id in range(1, NUM_USERS + 1):
            conn.execute(
                text("""
                    INSERT INTO room_members (room_id, user_id, role, joined_at)
                    VALUES (1, :user_id, 'MEMBER', NOW())
                    ON CONFLICT DO NOTHING;
                """),
                {"user_id": user_id}
            )

    print("-> Đã nạp thành công 500 Users & Room Members vào Database Local!")

    # 4. Xuất file tokens.csv cho JMeter
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    tokens_data = []
    print(f"-> Đang sinh {NUM_USERS} JWT Token Offline...")

    for user_id in range(1, NUM_USERS + 1):
        expire = datetime.now(timezone.utc) + timedelta(days=7)
        payload = {
            "sub": str(user_id),
            "exp": int(expire.timestamp()),
            "type": "access"
        }
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        tokens_data.append({"token": token, "user_id": user_id})

    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["token", "user_id"])
        writer.writeheader()
        writer.writerows(tokens_data)

    print(f"=== XONG! Đã nạp DB và xuất {len(tokens_data)} token ra: {OUTPUT_CSV} ===")


if __name__ == "__main__":
    seed_database_and_tokens()
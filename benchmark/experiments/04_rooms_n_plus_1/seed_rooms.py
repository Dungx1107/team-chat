"""Thêm dữ liệu riêng cho thí nghiệm N+1 danh sách phòng.

Chạy SAU shared/seed_data.py (seed chung xóa sạch DB), trong container của môi trường đo:

    docker compose -f docker-compose.bench.yml run --rm backend \
        python /benchmark/experiments/04_rooms_n_plus_1/seed_rooms.py

Mỗi mức trong ROOM_LEVELS có một user riêng tham gia đúng ngần ấy phòng, mỗi phòng
có MESSAGES_PER_ROOM tin. Token ghi ra data/tokens_rooms.csv.
"""
import csv
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.infra.db.session import engine  # noqa: E402
from app.infra.security.jwt import create_access_token  # noqa: E402

ROOM_LEVELS = [10, 50, 100, 200]
MESSAGES_PER_ROOM = 20
MEMBERS_PER_ROOM = 5          # chủ thể + 4 người khác, để member_count có ý nghĩa
EMAIL_PREFIX = "n1bench"
OUTPUT_CSV = Path(__file__).resolve().parent / "data" / "tokens_rooms.csv"


def _insert_user(conn, email: str, username: str) -> int:
    return conn.execute(
        text("""
            INSERT INTO users (email, username, first_name, last_name, password_hash, is_active, created_at)
            VALUES (:email, :username, 'Bench', :username, 'dummy_hash_for_test', true, NOW())
            RETURNING id
        """),
        {"email": email, "username": username},
    ).scalar_one()


def seed():
    url = settings.DATABASE_URL.lower()
    if "supabase" in url or "pooler" in url:
        sys.exit("TỪ CHỐI: DATABASE_URL trỏ vào Supabase. Chỉ chạy trong docker-compose.bench.yml.")

    rows = []
    with engine.begin() as conn:
        # Chạy lại được: xóa dữ liệu cũ của thí nghiệm; phòng, thành viên, tin theo CASCADE
        conn.execute(text("DELETE FROM users WHERE email LIKE :p"), {"p": f"{EMAIL_PREFIX}%"})

        extras = [
            _insert_user(conn, f"{EMAIL_PREFIX}_extra{i}@benchmark.com", f"{EMAIL_PREFIX}_extra{i}")
            for i in range(MEMBERS_PER_ROOM - 1)
        ]

        for level in ROOM_LEVELS:
            user_id = _insert_user(conn, f"{EMAIL_PREFIX}_{level}@benchmark.com", f"{EMAIL_PREFIX}_{level}")
            for r in range(level):
                room_id = conn.execute(
                    text("""
                        INSERT INTO rooms (name, owner_id, is_private, created_at)
                        VALUES (:name, :owner, false, NOW()) RETURNING id
                    """),
                    {"name": f"{EMAIL_PREFIX} {level}-{r}", "owner": user_id},
                ).scalar_one()
                members = [(user_id, "OWNER")] + [(e, "MEMBER") for e in extras]
                conn.execute(
                    text("""
                        INSERT INTO room_members (room_id, user_id, role, joined_at)
                        VALUES (:room_id, :user_id, :role, NOW())
                    """),
                    [{"room_id": room_id, "user_id": u, "role": role} for u, role in members],
                )
                conn.execute(
                    text("""
                        INSERT INTO messages (room_id, user_id, content, message_type, is_deleted, pinned, created_at)
                        VALUES (:room_id, :user_id, :content, 'TEXT', false, false,
                                NOW() - make_interval(secs => :age))
                    """),
                    [
                        {"room_id": room_id, "user_id": members[m % len(members)][0],
                         "content": f"tin {m}", "age": MESSAGES_PER_ROOM - m}
                        for m in range(MESSAGES_PER_ROOM)
                    ],
                )

            token = create_access_token(user_id, timedelta(days=7))
            rows.append({"rooms": level, "user_id": user_id, "token": token})
            print(f"-> User {user_id}: {level} phòng x {MESSAGES_PER_ROOM} tin")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["rooms", "user_id", "token"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"=== XONG! Token ghi ra {OUTPUT_CSV} ===")


if __name__ == "__main__":
    seed()

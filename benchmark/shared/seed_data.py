"""Tạo dữ liệu ảo dùng chung cho mọi phép đo (môi trường docker-compose.bench.yml).

Chạy TRONG container backend của môi trường đo, để dùng đúng DB và đúng key JWT:

    docker compose -f docker-compose.bench.yml run --rm backend \
        python /benchmark/shared/seed_data.py

Bố trí: 40 nhóm x 50 user. Mỗi nhóm có 10 phòng riêng, cả 50 người ở trong cả 10 phòng.

    Nhóm 1 : user    1 -   50  ->  phòng   1 -  10
    Nhóm 2 : user   51 -  100  ->  phòng  11 -  20
    ...
    Nhóm 40: user 1951 - 2000  ->  phòng 391 - 400

Đo ở mức N người dùng thì chỉ dùng N user đầu (N/50 nhóm đầu). Mọi user ở mọi mức
đều thấy cùng hoàn cảnh: 10 phòng, mỗi phòng 50 người. Chỉ số người đồng thời thay đổi.

Mỗi lần chạy XÓA SẠCH DB đo rồi tạo lại, kết quả giống hệt nhau giữa các lần (id cố
định, hạt giống ngẫu nhiên cố định). Từ chối chạy nếu DATABASE_URL trỏ vào Supabase.

Ghi ra benchmark/shared/data/ (không commit):
    tokens.csv      token,user_id,group_id,room_id,room_first,room_last
                    room_id: phòng "nhà" của user, trải đều 10 phòng của nhóm
                    room_first..room_last: 10 phòng user được vào
                    Thứ tự theo user_id: N dòng đầu = N user của mức tải N
    users.csv       user_id,email,password -- cho kịch bản đăng nhập
    files/          tệp mẫu 100 KB, 1 MB để thử tải lên
    seed_info.json  bố trí và số lượng đã tạo, để ghi kèm báo cáo

Thử nhanh với dữ liệu nhỏ:  --groups 2 --messages 20
"""
import argparse
import csv
import io
import json
import os
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import insert, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.infra.db.session import Base, engine  # noqa: E402
from app.infra.db.models import (  # noqa: E402
    UserModel, RoomModel, RoomMemberModel, MessageModel, AttachmentModel,
)
from app.infra.security.jwt import create_access_token  # noqa: E402
from app.infra.security.password import hash_password  # noqa: E402
from app.infra.storage.local_storage import LocalFileStorage  # noqa: E402

DEFAULTS = dict(
    groups=40,             # số nhóm -> tổng user = groups x group_size
    group_size=50,         # user mỗi nhóm = thành viên mỗi phòng
    rooms_per_group=10,    # phòng mỗi nhóm = số phòng mỗi user
    messages=250,          # tin mỗi phòng
    attachments=5,         # trong số đó, bao nhiêu tin có tệp
)

BENCH_PASSWORD = "Bench@12345"
ATTACHMENT_SIZES = [4 * 1024, 32 * 1024, 256 * 1024]
SAMPLE_UPLOAD_SIZES = {"sample_100KB.bin": 100 * 1024, "sample_1MB.bin": 1024 * 1024}
RANDOM_SEED = 42
CHUNK = 5000

DATA_DIR = Path(__file__).resolve().parent / "data"


def _guard():
    url = settings.DATABASE_URL.lower()
    if "supabase" in url or "pooler" in url:
        sys.exit("TỪ CHỐI: DATABASE_URL trỏ vào Supabase. Chỉ chạy trong docker-compose.bench.yml.")
    if settings.STORAGE_BACKEND != "local":
        sys.exit("TỪ CHỐI: STORAGE_BACKEND phải là 'local' trong môi trường đo.")


def _insert_chunks(conn, table, rows):
    for i in range(0, len(rows), CHUNK):
        conn.execute(insert(table), rows[i:i + CHUNK])


def _reset(conn):
    Base.metadata.create_all(bind=conn)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    try:
        with conn.begin_nested():
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
    except Exception:
        print("   (bỏ qua pg_stat_statements: DB không nạp sẵn extension này)")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    for f in upload_dir.iterdir():
        if f.is_file():
            f.unlink()


def _sync_sequence(conn, table: str):
    # Đã chèn id thủ công: đẩy bộ đếm lên để app tạo user/phòng mới không bị trùng id
    conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}))"))


def group_users(g: int, cfg: dict) -> range:
    start = (g - 1) * cfg["group_size"] + 1
    return range(start, start + cfg["group_size"])


def group_rooms(g: int, cfg: dict) -> range:
    start = (g - 1) * cfg["rooms_per_group"] + 1
    return range(start, start + cfg["rooms_per_group"])


def seed(cfg: dict):
    _guard()
    rng = random.Random(RANDOM_SEED)
    now = datetime.utcnow()
    storage = LocalFileStorage(settings.UPLOAD_DIR)
    n_users = cfg["groups"] * cfg["group_size"]
    n_rooms = cfg["groups"] * cfg["rooms_per_group"]
    print(f"-> Bố trí: {cfg} => {n_users} user, {n_rooms} phòng")

    with engine.begin() as conn:
        print("-> Xóa sạch DB đo và thư mục tệp")
        _reset(conn)

        # bcrypt 12 vòng tốn ~0.3 s mỗi lần: băm một lần, dùng chung cho mọi user
        pw_hash = hash_password(BENCH_PASSWORD)
        _insert_chunks(conn, UserModel.__table__, [
            dict(id=u, email=f"user{u}@benchmark.com", username=f"user_{u}", password_hash=pw_hash,
                 first_name="User", last_name=str(u), is_active=True, created_at=now)
            for u in range(1, n_users + 1)
        ])
        _sync_sequence(conn, "users")

        rooms, members = [], []
        for g in range(1, cfg["groups"] + 1):
            users = list(group_users(g, cfg))
            for i, room_id in enumerate(group_rooms(g, cfg)):
                # Chủ phòng xoay vòng trong nhóm để vai trò không dồn vào một người
                owner = users[i % len(users)]
                rooms.append(dict(id=room_id, name=f"Nhóm {g} - Phòng {i + 1}", owner_id=owner,
                                  is_private=False, created_at=now))
                members += [dict(room_id=room_id, user_id=u, joined_at=now,
                                 role="OWNER" if u == owner else "MEMBER") for u in users]
        _insert_chunks(conn, RoomModel.__table__, rooms)
        _sync_sequence(conn, "rooms")
        _insert_chunks(conn, RoomMemberModel.__table__, members)
        print(f"-> Tạo {n_users} user, {n_rooms} phòng, {len(members)} lượt thành viên")

        message_rows, n_messages, n_files = [], 0, 0
        n_msg = cfg["messages"]
        step = timedelta(days=30) / max(n_msg, 1)
        for g in range(1, cfg["groups"] + 1):
            users = list(group_users(g, cfg))
            for room_id in group_rooms(g, cfg):
                file_slots = set(rng.sample(range(n_msg), min(cfg["attachments"], n_msg)))
                for m in range(n_msg):
                    sender = rng.choice(users)
                    # Tin trải đều trong 30 ngày qua, cũ trước mới sau
                    row = dict(room_id=room_id, user_id=sender, content=f"Tin nhắn thử {m + 1}",
                               message_type="TEXT", is_deleted=False, pinned=False,
                               created_at=now - timedelta(days=30) + step * m, attachment_id=None)
                    if m in file_slots:
                        size = ATTACHMENT_SIZES[n_files % len(ATTACHMENT_SIZES)]
                        stored_name, real_size = storage.save(io.BytesIO(os.urandom(size)), "tep.bin")
                        row["attachment_id"] = conn.execute(
                            insert(AttachmentModel.__table__).returning(AttachmentModel.__table__.c.id),
                            dict(filename=f"tep_{n_files + 1}.bin", stored_name=stored_name,
                                 content_type="application/octet-stream", size_bytes=real_size,
                                 uploaded_by=sender, created_at=row["created_at"]),
                        ).scalar_one()
                        row["message_type"], row["content"] = "FILE", ""
                        n_files += 1
                    message_rows.append(row)
            # Ghi theo từng nhóm để không giữ cả 100 nghìn tin trong RAM
            _insert_chunks(conn, MessageModel.__table__, message_rows)
            n_messages += len(message_rows)
            message_rows = []
        print(f"-> Tạo {n_messages} tin nhắn, {n_files} tệp đính kèm")

    _write_outputs(cfg, n_users, n_rooms, len(members), n_messages, n_files)


def _write_outputs(cfg, n_users, n_rooms, n_members, n_messages, n_files):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"-> Sinh {n_users} token (7 ngày, key của môi trường đo)")
    with open(DATA_DIR / "tokens.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["token", "user_id", "group_id", "room_id", "room_first", "room_last"])
        for g in range(1, cfg["groups"] + 1):
            rooms = group_rooms(g, cfg)
            for i, u in enumerate(group_users(g, cfg)):
                # Phòng "nhà" trải đều: 50 người / 10 phòng = 5 người gửi vào mỗi phòng
                home = rooms[i % len(rooms)]
                w.writerow([create_access_token(u, timedelta(days=7)), u, g, home, rooms[0], rooms[-1]])

    with open(DATA_DIR / "users.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "email", "password"])
        for u in range(1, n_users + 1):
            w.writerow([u, f"user{u}@benchmark.com", BENCH_PASSWORD])

    files_dir = DATA_DIR / "files"
    if files_dir.exists():
        shutil.rmtree(files_dir)
    files_dir.mkdir()
    for name, size in SAMPLE_UPLOAD_SIZES.items():
        (files_dir / name).write_bytes(os.urandom(size))

    info = dict(layout=cfg, random_seed=RANDOM_SEED, password=BENCH_PASSWORD,
                created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                counts=dict(users=n_users, rooms=n_rooms, memberships=n_members,
                            messages=n_messages, attachments=n_files))
    (DATA_DIR / "seed_info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"=== XONG! {info['counts']} -> {DATA_DIR} ===")


def main():
    parser = argparse.ArgumentParser(description="Tạo dữ liệu ảo cho môi trường đo")
    for key, value in DEFAULTS.items():
        parser.add_argument(f"--{key.replace('_', '-')}", dest=key, type=int, default=value)
    seed(vars(parser.parse_args()))


if __name__ == "__main__":
    main()

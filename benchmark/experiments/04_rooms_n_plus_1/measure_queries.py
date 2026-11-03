"""Đếm số truy vấn SQL và đo thời gian của danh sách phòng: cách cũ (N+1) và cách mới.

Chạy cả hai cách trong cùng một tiến trình, trên cùng DB và dữ liệu, nên chỉ khác
nhau đúng một thay đổi. Cách cũ được chép nguyên từ router trước commit 5f3b655.

Chạy trong container của môi trường đo, sau seed_rooms.py:
    docker compose -f docker-compose.bench.yml run --rm backend \
        python /benchmark/experiments/04_rooms_n_plus_1/measure_queries.py

Tùy chọn mô phỏng độ trễ mạng tới DB (ví dụ Supabase ở Singapore):
    BENCH_RTT_MS=30
"""
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from app.config import settings  # noqa: E402
from app.repositories.room_repo import RoomRepository  # noqa: E402

HERE = Path(__file__).resolve().parent
RTT_MS = float(os.getenv("BENCH_RTT_MS", "0"))
REPEATS = int(os.getenv("BENCH_REPEATS", "30"))
WARMUP = 3


def before(repo, user_id):
    """Router list_rooms TRƯỚC cải tiến: 3 lời gọi repo cho mỗi phòng."""
    rooms = repo.list_joined_by_user(user_id, limit=500)
    out = {}
    for r in rooms:
        member = repo.get_member(r.id, user_id)
        out[r.id] = {
            "my_role": member.role if member else None,
            "member_count": repo.count_members(r.id),
            "last_message": repo.get_last_message_summary(r.id),
        }
    return out


def after(repo, user_id):
    """Router list_rooms SAU cải tiến."""
    rooms = repo.list_joined_by_user(user_id, limit=500)
    return repo.summarize_rooms([r.id for r in rooms], user_id)


def main():
    engine = create_engine(settings.DATABASE_URL)
    counter = {"q": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _count(*_):
        counter["q"] += 1
        if RTT_MS:
            time.sleep(RTT_MS / 1000)

    db = sessionmaker(bind=engine)()
    repo = RoomRepository(db)

    with open(HERE / "data" / "tokens_rooms.csv", encoding="utf-8") as f:
        users = [(int(r["rooms"]), int(r["user_id"])) for r in csv.DictReader(f)]

    results = []
    for rooms, user_id in users:
        assert before(repo, user_id) == after(repo, user_id), f"Kết quả khác nhau ở mức {rooms} phòng"
        entry = {"rooms": rooms, "rtt_ms": RTT_MS}
        for label, fn in (("before", before), ("after", after)):
            for _ in range(WARMUP):
                fn(repo, user_id)
            times = []
            for _ in range(REPEATS):
                counter["q"] = 0
                t = time.perf_counter()
                fn(repo, user_id)
                times.append((time.perf_counter() - t) * 1000)
            times.sort()
            entry[label] = {
                "queries": counter["q"],
                "median_ms": round(statistics.median(times), 2),
                "p95_ms": round(times[int(len(times) * 0.95) - 1], 2),
            }
        results.append(entry)
        b, a = entry["before"], entry["after"]
        print(f"{rooms:4} phòng | trước: {b['queries']:4} truy vấn, {b['median_ms']:8.2f} ms"
              f" | sau: {a['queries']} truy vấn, {a['median_ms']:7.2f} ms"
              f" | nhanh hơn {b['median_ms'] / a['median_ms']:.1f}x")

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"queries_rtt{int(RTT_MS)}ms.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"=== Đã lưu {out_file} ===")


if __name__ == "__main__":
    main()

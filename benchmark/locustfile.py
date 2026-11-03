"""Kịch bản Locust dùng chung cho mọi phép đo. Không chạy trực tiếp: dùng run_load.py.

Mỗi người dùng ảo giữ CỐ ĐỊNH một user của tokens.csv (token, phòng của nhóm mình),
lặp lại đúng MỘT hành động theo BENCH_SCENARIO, nghỉ BENCH_THINK_S giây giữa hai lần:

    rooms    GET  /api/rooms                         danh sách 10 phòng của mình
    history  GET  /api/rooms/{id}/messages?limit=50  một phòng ngẫu nhiên trong 10 phòng
    send     POST /api/rooms/{id}/messages           phòng "nhà" (~5 người/phòng cùng gửi)
    upload   POST /api/rooms/{id}/messages/upload    tệp 100 KB vào phòng ngẫu nhiên

Ghi từng request sau BENCH_SKIP_SECONDS giây đầu ra BENCH_SAMPLES_DIR, để run_load.py
gộp các tiến trình và tính số liệu chỉ trên đoạn đã ổn định.
"""
import csv
import json
import os
import random
import time
import uuid
from pathlib import Path

from locust import FastHttpUser, constant, events, task

HERE = Path(__file__).resolve().parent
SCENARIO = os.environ.get("BENCH_SCENARIO", "send")
TOKENS_FILE = Path(os.environ.get("BENCH_TOKENS", HERE / "shared" / "data" / "tokens.csv"))
UPLOAD_FILE = HERE / "shared" / "data" / "files" / "sample_100KB.bin"
THINK_S = float(os.environ.get("BENCH_THINK_S", "1"))
SKIP_SECONDS = float(os.environ.get("BENCH_SKIP_SECONDS", "10"))
SAMPLES_DIR = os.environ.get("BENCH_SAMPLES_DIR")

# Nhiều tiến trình Locust: tiến trình i lấy các dòng i, i+n, i+2n... Locust chia đều
# người dùng ảo cho các tiến trình, nên u người dùng ảo luôn là đúng u user đầu.
WORKER_INDEX = int(os.environ.get("BENCH_WORKER_INDEX", "0"))
WORKER_COUNT = int(os.environ.get("BENCH_WORKER_COUNT", "1"))

with open(TOKENS_FILE, encoding="utf-8") as f:
    _ROWS = list(csv.DictReader(f))[WORKER_INDEX::WORKER_COUNT]
_next_row = iter(_ROWS)

_samples = []
_measure_from = None


def _multipart(path: Path):
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


if SCENARIO == "upload":
    _UPLOAD_BODY, _UPLOAD_TYPE = _multipart(UPLOAD_FILE)


@events.request.add_listener
def _on_request(name, response_time, exception, start_time=None, **_):
    global _measure_from
    started = start_time or time.time()
    # Mốc bắt đầu tính từ request đầu tiên của tiến trình này; test_start không
    # được gửi tới worker khi chạy nhiều tiến trình
    if _measure_from is None:
        _measure_from = started + SKIP_SECONDS
    if started >= _measure_from:
        _samples.append((started, response_time, exception is None,
                         None if exception is None else type(exception).__name__ + ": " + str(exception)[:80]))


@events.quitting.add_listener
def _on_quit(environment, **_):
    if SAMPLES_DIR:
        out = Path(SAMPLES_DIR) / f"samples_{WORKER_INDEX}.json"
        out.write_text(json.dumps(_samples), encoding="utf-8")


class ChatUser(FastHttpUser):
    wait_time = constant(THINK_S)

    def on_start(self):
        try:
            me = next(_next_row)
        except StopIteration:
            raise RuntimeError("Nhiều người dùng ảo hơn số user trong tokens.csv") from None
        self.auth = {"Authorization": f"Bearer {me['token']}"}
        self.home_room = me["room_id"]
        self.rooms = range(int(me["room_first"]), int(me["room_last"]) + 1)

    @task
    def act(self):
        if SCENARIO == "rooms":
            self.client.get("/api/rooms", headers=self.auth, name="GET rooms")
        elif SCENARIO == "history":
            room = random.choice(self.rooms)
            self.client.get(f"/api/rooms/{room}/messages?limit=50", headers=self.auth, name="GET history")
        elif SCENARIO == "send":
            self.client.post(f"/api/rooms/{self.home_room}/messages", headers=self.auth,
                             json={"content": "Tin nhắn đo tải"}, name="POST message")
        elif SCENARIO == "upload":
            room = random.choice(self.rooms)
            self.client.post(f"/api/rooms/{room}/messages/upload", data=_UPLOAD_BODY,
                             headers={**self.auth, "Content-Type": _UPLOAD_TYPE}, name="POST upload")
        else:
            raise RuntimeError(f"BENCH_SCENARIO không hợp lệ: {SCENARIO}")

"""Kịch bản Locust dùng chung cho mọi phép đo. Không chạy trực tiếp: dùng run_load.py.

Mỗi người dùng ảo giữ CỐ ĐỊNH một user của tokens.csv (token, phòng của nhóm mình),
lặp lại đúng MỘT hành động theo BENCH_SCENARIO, nghỉ BENCH_THINK_S giây giữa hai lần:

    rooms    GET  /api/rooms                         danh sách 10 phòng của mình
    history  GET  /api/rooms/{id}/messages?limit=50  một phòng ngẫu nhiên trong 10 phòng
    send     POST /api/rooms/{id}/messages           phòng "nhà" (~5 người/phòng cùng gửi)
    upload   POST /api/rooms/{id}/messages/upload    tệp 100 KB vào phòng ngẫu nhiên
    rooms_mixed  mỗi vòng: BENCH_WRITE_RATIO (mặc định 20%) gửi tin vào phòng "nhà",
                 còn lại xem danh sách phòng -- đo cache khi dữ liệu đổi liên tục

    session  một phiên dùng app thật, đi đúng luồng gọi API của frontend:
             - mở app: hồ sơ, danh sách phòng, lời mời, rồi mở phòng "nhà"
               (mở phòng = lịch sử 50 tin + tin ghim + thành viên)
             - sau đó, cách nhau ngẫu nhiên trung bình ~23 giây, chọn theo SESSION_RATES:
               gửi tin ~45 s/lần (5% là tệp 100 KB), reaction ~2 phút/lần,
               chuyển phòng ~90 s/lần (3 phòng đầu nhóm "hay dùng" gấp 5 lần),
               tải lại trang (= mở app lại) ~10 phút/lần
             Tin mới đến qua WebSocket nên KHÔNG gọi lại lịch sử khi đang ở trong phòng.

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

from locust import FastHttpUser, events, task

HERE = Path(__file__).resolve().parent
SCENARIO = os.environ.get("BENCH_SCENARIO", "send")
TOKENS_FILE = Path(os.environ.get("BENCH_TOKENS", HERE / "shared" / "data" / "tokens.csv"))
UPLOAD_FILE = HERE / "shared" / "data" / "files" / "sample_100KB.bin"
THINK_S = float(os.environ.get("BENCH_THINK_S", "1"))
WRITE_RATIO = float(os.environ.get("BENCH_WRITE_RATIO", "0.2"))
SKIP_SECONDS = float(os.environ.get("BENCH_SKIP_SECONDS", "10"))
SAMPLES_DIR = os.environ.get("BENCH_SAMPLES_DIR")

# Số lần mỗi hành động trong một phút của MỘT người dùng (kịch bản session)
SESSION_RATES = {"send": 60 / 45, "react": 60 / 120, "switch": 60 / 90, "reload": 60 / 600}
SESSION_MEAN_GAP_S = 60 / sum(SESSION_RATES.values())
FILE_RATIO = 0.05
HOT_ROOMS, HOT_WEIGHT = 3, 5
EMOJIS = ("👍", "❤️", "😂", "😮", "😢", "🎉")

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


if SCENARIO in ("upload", "session"):
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
                         None if exception is None else type(exception).__name__ + ": " + str(exception)[:80],
                         name))


@events.quitting.add_listener
def _on_quit(environment, **_):
    # Tiến trình master (chỉ số -1) không gửi request nào: không ghi, tránh ghi chồng
    # lúc run_load.py đang dọn thư mục tạm
    if SAMPLES_DIR and WORKER_INDEX >= 0:
        out = Path(SAMPLES_DIR) / f"samples_{WORKER_INDEX}.json"
        out.write_text(json.dumps(_samples), encoding="utf-8")


class ChatUser(FastHttpUser):
    def wait_time(self):
        if SCENARIO == "session":
            # Khoảng cách giữa hai hành động của người thật không đều: phân bố mũ
            return random.expovariate(1 / SESSION_MEAN_GAP_S)
        return THINK_S

    def on_start(self):
        try:
            me = next(_next_row)
        except StopIteration:
            raise RuntimeError("Nhiều người dùng ảo hơn số user trong tokens.csv") from None
        self.auth = {"Authorization": f"Bearer {me['token']}"}
        self.home_room = me["room_id"]
        self.rooms = range(int(me["room_first"]), int(me["room_last"]) + 1)
        if SCENARIO == "session":
            self.room_weights = [HOT_WEIGHT if i < HOT_ROOMS else 1 for i in range(len(self.rooms))]
            self.message_ids = []
            self.open_app()

    # ---------- Kịch bản session ----------

    def open_app(self):
        """Mở app hoặc tải lại trang: đúng các request frontend gọi lúc khởi động."""
        self.client.get("/api/users/me", headers=self.auth, name="GET me")
        self.client.get("/api/rooms", headers=self.auth, name="GET rooms")
        self.client.get("/api/rooms/notifications/invites", headers=self.auth, name="GET invites")
        self.open_room(int(self.home_room))

    def open_room(self, room_id: int):
        self.current_room = room_id
        with self.client.get(f"/api/rooms/{room_id}/messages?limit=50&offset=0", headers=self.auth,
                             name="GET history", catch_response=True) as r:
            try:
                self.message_ids = [m["id"] for m in r.json()] if r.ok else []
            except Exception:
                self.message_ids = []
        self.client.get(f"/api/rooms/{room_id}/pinned-messages", headers=self.auth, name="GET pinned")
        self.client.get(f"/api/rooms/{room_id}/members", headers=self.auth, name="GET members")

    def session_step(self):
        action = random.choices(list(SESSION_RATES), weights=list(SESSION_RATES.values()))[0]
        if action == "react" and not self.message_ids:
            action = "send"
        if action == "send":
            if random.random() < FILE_RATIO:
                self.client.post(f"/api/rooms/{self.current_room}/messages/upload", data=_UPLOAD_BODY,
                                 headers={**self.auth, "Content-Type": _UPLOAD_TYPE}, name="POST upload")
            else:
                self.client.post(f"/api/rooms/{self.current_room}/messages", headers=self.auth,
                                 json={"content": "Tin nhắn đo tải"}, name="POST message")
        elif action == "react":
            self.client.post(f"/api/messages/{random.choice(self.message_ids)}/reactions", headers=self.auth,
                             json={"emoji": random.choice(EMOJIS)}, name="POST reaction")
        elif action == "switch":
            self.open_room(random.choices(list(self.rooms), weights=self.room_weights)[0])
        else:
            self.open_app()

    @task
    def act(self):
        if SCENARIO == "session":
            self.session_step()
        elif SCENARIO == "rooms":
            self.client.get("/api/rooms", headers=self.auth, name="GET rooms")
        elif SCENARIO == "rooms_mixed":
            if random.random() < WRITE_RATIO:
                self.client.post(f"/api/rooms/{self.home_room}/messages", headers=self.auth,
                                 json={"content": "Tin nhắn đo tải"}, name="POST message")
            else:
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

# Đo hiệu năng

Mọi phép đo chạy trong **môi trường đo riêng** (`docker-compose.bench.yml` ở gốc repo),
tách hẳn khỏi production:

| | Production (`docker-compose.yml`) | Môi trường đo (`docker-compose.bench.yml`) |
|---|---|---|
| Database | Supabase (dữ liệu thật) | Postgres local, cổng `5433`, chỉ chứa user ảo |
| Lưu tệp | Supabase Storage | Volume `bench_uploads` (`STORAGE_BACKEND=local`) |
| Cấu hình | `.env` | Ghi thẳng trong file compose, **không** đọc `.env` |
| Key JWT | key thật | key riêng: token đo không dùng được trên production |
| Backend | qua nginx, cổng 443 | gọi thẳng, cổng `8001` |
| Số worker | 1 | `BENCH_WORKERS` (mặc định 1) |

Hai môi trường chạy song song được: khác tên project, tên container và cổng.

## Chạy

```bash
# 1. Dựng môi trường đo
docker compose -f docker-compose.bench.yml up -d --build

# 2. Tạo dữ liệu ảo (XÓA SẠCH DB đo rồi tạo lại)
docker compose -f docker-compose.bench.yml run --rm backend \
    python /benchmark/shared/seed_data.py

# 3. Kiểm tra
curl http://localhost:8001/health

# Dừng (giữ dữ liệu) / xóa sạch
docker compose -f docker-compose.bench.yml down
docker compose -f docker-compose.bench.yml down -v
```

Đổi số worker: `BENCH_WORKERS=4 docker compose -f docker-compose.bench.yml up -d`.

## Dữ liệu ảo — `shared/seed_data.py`

Một bố trí duy nhất cho cả nhóm: **40 nhóm × 50 user, mỗi nhóm 10 phòng riêng**, cả 50
người ở trong cả 10 phòng.

```
Nhóm 1 : user    1 -   50  ->  phòng   1 -  10
Nhóm 2 : user   51 -  100  ->  phòng  11 -  20
...
Nhóm 40: user 1951 - 2000  ->  phòng 391 - 400
```

| | |
|---|---|
| Tổng | 2000 user, 400 phòng, 100 000 tin, 2000 tệp đính kèm |
| Mỗi user | ở 10 phòng |
| Mỗi phòng | 50 thành viên, 250 tin (5 tin có tệp) |

**Mức tải N người dùng chỉ dùng N user đầu**, tức N/50 nhóm đầu: mức 50 là nhóm 1, mức
500 là nhóm 1–10. Ở mọi mức, mỗi người dùng thấy cùng hoàn cảnh (10 phòng × 50 người),
chỉ số người đồng thời thay đổi. Dữ liệu nạp một lần, DB to như nhau ở mọi mức.

- Mỗi lần chạy **xóa sạch DB đo** rồi tạo lại, kết quả giống hệt nhau giữa các lần.
- Thử nhanh với dữ liệu nhỏ: `--groups 2 --messages 20`.
- Mật khẩu mọi user: `Bench@12345`, email `user<N>@benchmark.com`.
- Từ chối chạy nếu `DATABASE_URL` trỏ vào Supabase.

Sinh ra trong `shared/data/` (**không commit**, ai chạy seed thì tự có):

| Tệp | Dùng cho |
|---|---|
| `tokens.csv` | `token,user_id,group_id,room_id,room_first,room_last` — JWT 7 ngày. `room_id` là phòng "nhà" (trải đều 10 phòng của nhóm), `room_first..room_last` là 10 phòng được vào. Xếp theo `user_id` |
| `users.csv` | `user_id,email,password` — kịch bản đăng nhập |
| `files/` | Tệp mẫu 100 KB, 1 MB để thử tải lên |
| `seed_info.json` | Bố trí và số lượng đã tạo — ghi kèm vào báo cáo |

## Đo tải — Locust

```bash
pip install locust
python benchmark/run_load.py --scenario <kịch bản> --out <tệp kết quả.json>
```

`locustfile.py` có 4 kịch bản, mỗi lần đo **một** hành động:

| Kịch bản | Request | Phòng |
|---|---|---|
| `rooms` | `GET /api/rooms` | 10 phòng của mình |
| `history` | `GET /api/rooms/{id}/messages?limit=50` | ngẫu nhiên trong 10 phòng |
| `send` | `POST /api/rooms/{id}/messages` | phòng "nhà" (~5 người/phòng cùng gửi) |
| `upload` | `POST .../messages/upload`, tệp 100 KB | ngẫu nhiên trong 10 phòng |

**Mỗi người dùng ảo giữ cố định một user** (token, phòng của nhóm mình), làm hành động,
nghỉ 1 giây, lặp lại.

**Thang tải:** 50 → 100 → 200 → 500 → 1000 → 2000 người dùng (`--steps` để đổi). Mỗi mức:

```
0s ── lên đủ người (5s) ── 10s ─────── đo 60 giây ─────── 70s ── nghỉ 15s ── mức sau
     |--- bỏ, server còn khởi động ---|  CHỈ tính đoạn này
```

- Mức N chỉ dùng N user đầu = N/50 nhóm đầu.
- Lỗi quá 50% thì dừng, không đo các mức cao hơn.
- Mỗi mức ~85 giây, cả thang ~9 phút cho một kịch bản.
- Mặc định 4 tiến trình Locust (`--workers`): một tiến trình Python không đủ sức tạo
  2000 người dùng. Trên Windows script tự dựng master + worker.

**Kết quả JSON:** cho mỗi mức, request/giây, thời gian trung bình, trung vị, p95, p99, tối
đa, % lỗi và loại lỗi hay gặp. Kèm cấu hình đo và `seed_info.json` để biết đo trên dữ liệu
nào. Ghi thêm `--note "commit abc, 1 worker"` để khỏi quên đo bản nào.

**Kịch bản ghi dữ liệu** (`send`, `upload`) làm DB to dần: seed lại trước mỗi lần đo.

Thay đổi khác qua biến môi trường: `BENCH_HOST`, `BENCH_RAMP_UP`, `BENCH_SKIP_SECONDS`,
`BENCH_HOLD_SECONDS`, `BENCH_REST_SECONDS`, `BENCH_THINK_S`, `BENCH_STOP_ERROR_PCT`.

## Thí nghiệm

Mỗi cải tiến một thư mục trong `experiments/`, kết quả để trong `results/` của thư mục đó:

| Thư mục | Cải tiến | Kịch bản |
|---|---|---|
| `01_redis_pubsub/` | Redis Pub/Sub, nhiều worker | `send` |
| `04_rooms_n_plus_1/` | Bỏ N+1 ở danh sách phòng | `rooms` (+ đếm truy vấn SQL) |

Ví dụ đo trước/sau:

```bash
python benchmark/run_load.py --scenario send --note "1 worker, chưa Redis" \
    --out benchmark/experiments/01_redis_pubsub/results/before.json
```

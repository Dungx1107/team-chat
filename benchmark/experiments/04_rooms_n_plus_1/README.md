# 04 — Bỏ N+1 ở danh sách phòng

## Cải tiến

`GET /api/rooms` trước đây gọi `get_member`, `count_members`, `get_last_message_summary`
cho **từng phòng**: 1 + 4N truy vấn (hàm tin cuối tốn 2 truy vấn). Commit `5f3b655` thêm
`RoomRepository.summarize_rooms` lấy cả ba thông tin cho mọi phòng trong **3 truy vấn cố
định**, nên cả endpoint luôn tốn 4 truy vấn.

| | Commit |
|---|---|
| Trước | `backend/app/api/routers/rooms.py` lấy từ `f406d76` (vòng lặp cũ) |
| Sau | `rooms.py` hiện tại (gọi `summarize_rooms`) |

Chỉ đổi đúng file router, phần còn lại của backend giữ nguyên, nên hai bên chỉ khác
nhau đúng một thay đổi: cùng DB, cùng dữ liệu, cùng máy.

## Dữ liệu

Chạy trong môi trường đo ([`../../README.md`](../../README.md)). Sau seed chung,
`seed_rooms.py` thêm 4 user, mỗi user tham gia **10 / 50 / 100 / 200 phòng**. Mỗi phòng có
5 thành viên và 20 tin. Token ghi ra `data/tokens_rooms.csv`.

## Hai phép đo

### 1. Số truy vấn và thời gian xử lý — `measure_queries.py`

Chạy cách cũ và cách mới trong cùng một tiến trình, đếm truy vấn bằng sự kiện của
SQLAlchemy, kiểm tra hai cách trả kết quả **giống hệt nhau**, đo trung vị và p95 qua 30 lần.

`BENCH_RTT_MS=30` thêm 30 ms trễ cho mỗi truy vấn, mô phỏng DB ở xa như Supabase
Singapore. Đây là chỗ N+1 gây hại nhiều nhất.

```bash
B="docker compose -f docker-compose.bench.yml run --rm backend"
$B python /benchmark/shared/seed_data.py
$B python /benchmark/experiments/04_rooms_n_plus_1/seed_rooms.py
$B python /benchmark/experiments/04_rooms_n_plus_1/measure_queries.py
$B sh -c "BENCH_RTT_MS=30 BENCH_REPEATS=5 python /benchmark/experiments/04_rooms_n_plus_1/measure_queries.py"
```

Kết quả: `results/queries_rtt0ms.json`, `results/queries_rtt30ms.json`.

### 2. Tải HTTP — Locust, kịch bản `rooms`

Dùng dữ liệu chung (mỗi user 10 phòng) và thang 50 → 2000 người dùng. Bản "trước" chỉ
đổi lại đúng file router cũ:

```bash
git checkout f406d76 -- backend/app/api/routers/rooms.py
docker compose -f docker-compose.bench.yml restart backend
python benchmark/run_load.py --scenario rooms --out benchmark/experiments/04_rooms_n_plus_1/results/before.json

git checkout HEAD -- backend/app/api/routers/rooms.py
docker compose -f docker-compose.bench.yml restart backend
python benchmark/run_load.py --scenario rooms --out benchmark/experiments/04_rooms_n_plus_1/results/after.json
```

Kịch bản chỉ đọc nên không cần seed lại giữa hai lần.

## Kết quả

Xem `results/report_summary.md`.

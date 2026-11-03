# Báo cáo đo: baseline gửi tin nhắn (trước Redis Pub/Sub)

Ngày đo: 03/11/2026 · Người đo: Dat · Commit: `a42fa72` cùng các thay đổi môi trường đo
(sau đó commit ở `c4e132e`, `435ed3d`)

Đây là số liệu **trước** cải tiến Redis Pub/Sub. Phần **sau** sẽ do người làm cải tiến
đo bằng cùng kịch bản và dữ liệu.

## Tóm tắt

| | |
|---|---|
| Chịu tải tối đa (p95 < 1 s, lỗi < 1%) | **khoảng 100–120 người dùng đồng thời** |
| Throughput cao nhất | **khoảng 75–87 tin/giây** |
| Từ 150 người | **server kẹt hẳn**, không chậm dần |
| Nguyên nhân kẹt | bể kết nối DB cạn (`QueuePool limit of size 5 overflow 10`), CPU còn dư |

## 1. Môi trường

| | |
|---|---|
| Máy | Laptop Windows 11, Docker Desktop |
| Backend | `docker-compose.bench.yml`, **1 worker uvicorn**, chưa có Redis, bể kết nối mặc định 5 + 10 |
| DB | Postgres 16 trong Docker, cùng máy |
| Công cụ | Locust 2.47, 4 tiến trình |
| Dữ liệu | `shared/seed_data.py` mặc định: 2000 user, 40 nhóm × 50 người, mỗi nhóm 10 phòng; 100 000 tin |

Seed lại trước mỗi lượt đo vì kịch bản gửi tin làm DB to dần.

## 2. Kịch bản

`run_load.py --scenario send`: mỗi người dùng ảo là một user cố định, gửi
`POST /api/rooms/{phòng nhà}/messages`, nghỉ 1 giây, lặp lại. Phòng "nhà" trải đều 10
phòng của nhóm, khoảng 5 người cùng gửi vào một phòng, mỗi tin phát tới 50 thành viên.

Mỗi mức: lên đủ người trong 5 giây, **bỏ 10 giây đầu, chỉ tính 60 giây sau**, nghỉ 15
giây. Dừng khi lỗi quá 50%.

## 3. Kết quả

| Người dùng | req/s | Trung bình | Trung vị | p95 | p99 | Lỗi | Tệp |
|---|---|---|---|---|---|---|---|
| 50 | 47,7 | 42 ms | 25 ms | 140 ms | 261 ms | 0% | `before.json` |
| 100 | 73,2 | 352 ms | 248 ms | 1005 ms | 2102 ms | 0% | `before.json` |
| 120 (lần 1) \* | 87,4 | 343 ms | — | 711 ms | — | 0% | `before_120_150_run1_console.txt` |
| 120 (lần 2) | 74,4 | 559 ms | 495 ms | 1121 ms | 1502 ms | 0% | `before_120_150.json` |
| 150 (cả 2 lần) | ~0 | — | — | — | — | kẹt hẳn | `before_120_150*.json` |
| 200 | ~0 | — | — | — | — | kẹt hẳn | `before.json` |

\* Lần 1 mất tệp JSON do lỗi lệnh chạy nền; số liệu lấy từ dòng in ra màn hình.

**CPU lượt 50 / 100 / 200** (cao nhất / trung bình): backend 129% / 46%, DB 54% / 17%.

### Đọc kết quả

- Từ 50 lên 100 người, throughput chỉ tăng 48 → 73 req/s trong khi thời gian phản hồi
  tăng 8 lần: server đã gần bão hòa ở khoảng 75 req/s.
- Theo định luật Little (người dùng = throughput × (thời gian phản hồi + 1 s nghỉ)), nếu
  chỉ là xếp hàng thì 150 người lẽ ra p95 khoảng 2,5 s. Thực tế server **kẹt hẳn**: chỉ
  vài chục phản hồi trong hơn một phút, dồn thành đợt cách nhau đúng 30 giây (thời gian
  chờ kết nối của SQLAlchemy).
- CPU không cao khi kẹt, nên nút thắt không phải sức tính toán. Log có 563 lỗi
  `QueuePool limit` ở lượt 50 / 100 / 200 và 67 lỗi ở lượt 120 / 150 lần 2.
- Giả thuyết **chưa kiểm chứng**: FastAPI có 40 luồng cho endpoint đồng bộ, bể chỉ có 15
  kết nối. Khi cả 40 luồng chờ kết nối, việc trả kết nối về bể (`db.close()` trong
  `get_db`) cũng cần một luồng rảnh, nên không kết nối nào được trả cho tới khi hết hạn
  chờ 30 giây.

## 4. Hạn chế

- Mức 120 đo 2 lần, các mức khác 1 lần. Hai lần ở mức 120 lệch nhau (p95 711 so với
  1121 ms); lần 2 có thể bị ảnh hưởng bởi một vòng ghi `docker stats` của lần 1 còn chạy
  ngầm.
- Locust và server chạy chung một máy.
- Chưa đo 500 → 2000 người vì server đã kẹt từ 150.

## 5. Gợi ý cho phần "sau"

- Thêm Redis và nhiều worker mà **không** sửa bể kết nối thì nhiều khả năng vẫn kẹt ở
  khoảng 150–200 người. Nên sửa bể kết nối trước, hoặc đo riêng từng thay đổi để biết
  phần cải thiện đến từ đâu.
- Đo bằng đúng lệnh này để so sánh được:

```bash
docker compose -f docker-compose.bench.yml run --rm backend python /benchmark/shared/seed_data.py
python benchmark/run_load.py --scenario send --note "<mô tả bản đang đo>" \
    --out benchmark/experiments/01_redis_pubsub/results/after.json
```

## Tệp kết quả

| Tệp | Nội dung |
|---|---|
| `before.json`, `before_console.txt`, `before_resources.csv`, `before_backend.log.gz` | Lượt 50 / 100 / 200 |
| `before_120_150.json` và `before_120_150_*` | Lượt 120 / 150, lần 2 |
| `before_120_150_run1_*` | Lượt 120 / 150, lần 1 (không có JSON; tệp CPU ghi chồng sang thời gian lần 2) |

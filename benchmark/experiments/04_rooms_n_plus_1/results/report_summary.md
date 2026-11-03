# Báo cáo đo: bỏ N+1 ở danh sách phòng

Ngày đo: 03/11/2026 · Người đo: Dat · Commit cải tiến: `5f3b655`

## Tóm tắt

| | Trước | Sau |
|---|---|---|
| Số truy vấn SQL cho một lần mở danh sách phòng | **1 + 4N** (N = số phòng) | **4**, không phụ thuộc N |
| User có 10 phòng, DB local | 41 truy vấn, 58 ms | 4 truy vấn, 6 ms |
| User có 200 phòng, giả lập DB ở xa như Supabase | 801 truy vấn, **26 giây** | 4 truy vấn, **0,15 giây** |
| 50 người dùng đồng thời, p95 | **1983 ms** | **202 ms** |
| Chịu được 100 người dùng đồng thời | **Không**, server kẹt hẳn | **Có**, p95 450–489 ms, sát giới hạn |

Cải tiến loại bỏ hoàn toàn chi phí tăng theo số phòng. Khi tải cao, giới hạn tiếp theo
của hệ thống là **bể kết nối DB** (15 kết nối), không còn là truy vấn.

## 1. Cải tiến

`GET /api/rooms` trả danh sách phòng cho thanh bên, gọi mỗi khi mở app. Trước đây với
mỗi phòng, router gọi `get_member` (vai trò của tôi), `count_members` (số thành viên)
và `get_last_message_summary` (tin cuối, tự nó tốn 2 truy vấn): **1 + 4N truy vấn**.

`RoomRepository.summarize_rooms` lấy cả ba thông tin cho mọi phòng trong **3 truy vấn**
(`IN (...)`, `GROUP BY`, và `ROW_NUMBER() OVER (PARTITION BY room_id)` cho tin cuối).
Cả endpoint luôn tốn 4 truy vấn. Thay đổi chỉ nằm ở tầng repository và router.

## 2. Môi trường

| | |
|---|---|
| Máy | Laptop Windows 11, Docker Desktop |
| Backend | `docker-compose.bench.yml`, 1 worker uvicorn, bể kết nối SQLAlchemy mặc định 5 + 10 |
| DB | Postgres 16 trong Docker, cùng máy |
| Công cụ | Locust 2.47 (4 tiến trình), script `measure_queries.py` |

**Dữ liệu** (`shared/seed_data.py`): 2000 user chia 40 nhóm × 50 người, mỗi nhóm 10 phòng
riêng. Tổng 400 phòng, 100 000 tin, 2000 tệp. **Mỗi user ở đúng 10 phòng**, mỗi phòng 50
thành viên. Thêm 4 user ở 10 / 50 / 100 / 200 phòng cho phép đo số truy vấn
(`seed_rooms.py`).

**Trước và sau chỉ khác đúng một thứ:** bản "trước" chỉ thay file
`backend/app/api/routers/rooms.py` bằng bản ở commit `f406d76`. Cùng DB, cùng dữ liệu,
cùng máy, cùng phần còn lại của backend.

## 3. Phép đo 1: số truy vấn và thời gian xử lý

`measure_queries.py` chạy cách cũ và cách mới trong cùng một tiến trình, kiểm tra hai
cách trả về **kết quả giống hệt nhau**, đếm truy vấn bằng sự kiện của SQLAlchemy, đo 30
lần sau 3 lần khởi động.

**DB local** (`queries_rtt0ms.json`):

| Số phòng | Truy vấn trước | Truy vấn sau | Trung vị trước | Trung vị sau | p95 trước | p95 sau |
|---|---|---|---|---|---|---|
| 10 | 41 | 4 | 58 ms | 6 ms | 154 ms | 22 ms |
| 50 | 201 | 4 | 174 ms | 7 ms | 274 ms | 16 ms |
| 100 | 401 | 4 | 432 ms | 29 ms | 932 ms | 44 ms |
| 200 | 801 | 4 | 1016 ms | 15 ms | 3382 ms | 21 ms |

**Giả lập DB ở xa** (`queries_rtt30ms.json`): thêm 30 ms cho mỗi truy vấn, gần với một
lượt đi về Supabase ở Singapore. Đo 5 lần.

| Số phòng | Trung vị trước | Trung vị sau | Nhanh hơn |
|---|---|---|---|
| 10 | 1,33 s | 0,13 s | 10× |
| 50 | 6,56 s | 0,15 s | 45× |
| 100 | 13,15 s | 0,15 s | 86× |
| 200 | 26,17 s | 0,15 s | 179× |

Cách cũ tăng tuyến tính theo số phòng, cách mới gần như nằm ngang. DB càng xa, chênh
lệch càng lớn: production đang dùng Supabase nên đây là trường hợp thực tế.

## 4. Phép đo 2: tải đồng thời

`run_load.py --scenario rooms`: mỗi người dùng ảo là một user cố định, gọi
`GET /api/rooms`, nghỉ 1 giây, lặp lại. Mức N người dùng dùng N user đầu (N/50 nhóm đầu).
Mỗi mức: lên đủ người trong 5 giây, **bỏ 10 giây đầu, chỉ tính 60 giây sau**, nghỉ 15
giây. Dừng khi lỗi quá 50%.

| Người dùng | | req/s | Trung bình | Trung vị | p95 | p99 | Lỗi |
|---|---|---|---|---|---|---|---|
| 50 | Trước | 22,3 | 1186 ms | 1068 ms | **1983 ms** | 2433 ms | 0% |
| 50 | Sau | 46,9 | 58 ms | 25 ms | **202 ms** | 494 ms | 0% |
| 100 | Trước | — | — | — | — | — | **kẹt hẳn** |
| 100 | Sau, lần 1 \* | 79,6 | 214 ms | 190 ms | 450 ms | 570 ms | 0% |
| 100 | Sau, lần 2 | 34,4 | 894 ms | 177 ms | 489 ms | 30 565 ms | 1,46% |
| 200 | Sau | — | — | — | — | — | **kẹt hẳn** |

\* Lần 1 mất tệp JSON do lỗi của `run_load.py` (đã sửa ở commit `fix(bench)`). Số liệu
lấy từ bảng tổng của Locust trong `locust_after_run1_console.txt`, **tính cả 10 giây
đầu**, nên không cùng cách tính với các dòng khác.

**CPU** (cao nhất / trung bình, theo `docker stats` mỗi 5 giây):

| | Backend | DB |
|---|---|---|
| Trước | 129% / 55% | 69% / 31% |
| Sau | 119% / 28% | 69% / 15% |

### Đọc kết quả

- **Ở 50 người, p95 giảm khoảng 10 lần** (1983 → 202 ms). Throughput đạt 47 req/s, tức
  mỗi người dùng được phục vụ đúng 1 request/giây như kịch bản; bản trước chỉ được 22.
- **Bản trước kẹt ở 100 người, bản sau chạy được.** Mỗi request cũ chạy 41 truy vấn
  nên giữ kết nối DB lâu gấp nhiều lần, bể 15 kết nối cạn sớm hơn.
- **Ở 100 người, bản sau nằm sát giới hạn.** Lần 2 có 26 lỗi 500, toàn bộ là
  `QueuePool limit of size 5 overflow 10 reached` sau 30 giây chờ (p99 = 30,6 s). Hai lần
  đo lệch nhau, đúng kiểu hành vi ở mép giới hạn.
- **Ở 200 người, cả hai bản đều kẹt** vì cùng một nút thắt: bể kết nối DB. Giới hạn
  này không thuộc về cải tiến N+1 (xem thêm báo cáo `01_redis_pubsub`).

## 5. Hạn chế

- Mỗi mức chỉ đo 1 lần (riêng 100 người bản sau 2 lần). Ở mép giới hạn kết quả dao
  động; nên đo 3 lần và lấy trung vị.
- Locust và server chạy chung một máy, tranh CPU với nhau.
- Phép đo 1 với độ trễ 30 ms là **giả lập** bằng `time.sleep` trước mỗi truy vấn, chưa
  đo trên Supabase thật.
- Chưa đo các mức 500 → 2000 vì server đã kẹt từ 200.

## 6. Hướng tiếp theo

1. **Tăng bể kết nối DB** (`pool_size + max_overflow` ≥ 40 luồng của FastAPI) trong
   `backend/app/infra/db/session.py`. Đây là nút thắt chung của mọi API hiện nay.
2. Sau đó đo lại kịch bản `rooms` để xem giới hạn mới nằm ở đâu.

## Tệp kết quả

| Tệp | Nội dung |
|---|---|
| `queries_rtt0ms.json`, `queries_rtt30ms.json`, `queries_console.txt` | Phép đo 1 |
| `locust_before.json`, `locust_after.json` | Phép đo 2 |
| `locust_*_console.txt` | Output đầy đủ của Locust |
| `locust_*_resources.csv` | CPU/RAM backend và DB mỗi 5 giây |
| `locust_*_backend.log.gz` | Log backend trong lúc đo |
| `locust_after_run1_*` | Lần chạy hỏng của bản sau, giữ lại để đối chiếu |

Chạy lại: xem [`../README.md`](../README.md).

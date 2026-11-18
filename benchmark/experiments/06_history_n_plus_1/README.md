# 06 — Bỏ N+1 khi tải lịch sử chat

Ngày đo: 17–18/11/2026 · Người đo: Dat · Commit cải tiến: `794b709`

## Tóm tắt

| | Trước | Sau |
|---|---|---|
| Truy vấn SQL khi mở một phòng (50 tin) | **53** | **4** |
| Thời gian mở phòng, DB ở xa 90 ms | **5,3 giây** | **0,69 giây** |
| Phiên dùng app thật, 4 worker, p95 ở 100–500 người | **5,5–6,6 giây** | **1,1–1,3 giây** |
| Lỗi ở 1000 người dùng đồng thời | **15%** | **0,02%** |

Sửa N+1 lịch sử chat là cải tiến có tác dụng lớn nhất trong kịch bản sát thực tế: mở
phòng là thao tác người dùng làm liên tục, và mỗi lần mở trước đây giữ một kết nối DB
khoảng 5 giây.

## 1. Vấn đề và cách sửa

`GET /api/rooms/{id}/messages` lấy 50 tin, đã nạp sẵn người gửi, tệp đính kèm và
reaction trong một truy vấn (`joinedload`). Nhưng `MessageRepository._to_entity` lại hỏi
**biệt danh người gửi cho từng tin**: 50 tin = 50 truy vấn, cộng truy vấn chính và hai
lần kiểm tra quyền = 53.

Lỗi này không lộ ra ở các lần đo trước vì chúng chỉ đo danh sách phòng, và lúc đo với DB
cùng máy thì mỗi truy vấn chỉ mất vài mili giây. Kịch bản phiên dùng app thật (mở phòng)
cộng độ trễ 90 ms tới DB mới làm nó lộ rõ: 53 × 91 ms ≈ 4,8 giây.

Sửa: `_to_entities` lấy biệt danh của mọi người gửi trong trang bằng **một** truy vấn
(`user_id IN (...)`), dùng cho cả lịch sử và tin ghim. Gọi lẻ cho một tin (vừa gửi) vẫn
một truy vấn như cũ. Chỉ sửa tầng Repository; Service và Domain không đổi.

Cùng loại lỗi với cải tiến 04 (danh sách phòng): antipattern **Chatty I/O**, khắc phục
bằng **Batch Query**.

## 2. Kiểm tra đúng

So tên người gửi của **3000 tin** ở 20 phòng, mỗi phòng 3 trang (có đặt biệt danh cho
một phần thành viên ở 3 phòng) với cách cũ: **không lệch tin nào**, trong mẫu có 51 tin
hiển thị biệt danh.

## 3. Đo một request

Postgres local, giả lập độ trễ 90 ms tới DB (`tc netem`, bằng độ trễ thật tới Supabase
của nhóm ở Seoul). Mỗi bản 12 request tuần tự tới 10 phòng, bỏ 2 request đầu.
Bản "trước" chỉ thay đúng `message_repo.py` bằng bản ở `794b709^`.

| | Truy vấn | Trung vị | Thấp nhất | Cao nhất |
|---|---|---|---|---|
| Trước | 53 | 5320 ms | 5305 ms | 5334 ms |
| Sau | 4 | 694 ms | 660 ms | 733 ms |

Sau khi sửa vẫn cao hơn 4 × 91 ms vì mỗi request còn các lượt đi về khác (kiểm tra kết
nối khi mượn từ bể, kết thúc giao dịch).

## 4. Đo tải: phiên dùng app thật

Đo cùng thí nghiệm 05 (`benchmark/experiments/05_cache_aside/results/S2_*`):

- Hệ thống sau khi merge cải tiến của Dũng: **4 worker**, bể kết nối 20 + 30 mỗi worker,
  Redis Pub/Sub. Cache tắt.
- Postgres local + trễ 90 ms. Dữ liệu seed chung (2000 user, 400 phòng, 100 000 tin).
- Kịch bản `session`: 60 giây mọi người lần lượt mở app, 240 giây chat như người thật
  (gửi tin ~45 s/lần, chuyển phòng ~90 s/lần, reaction, tệp, F5 ~10 phút/lần).
- Bản "trước" và "sau" chỉ khác `message_repo.py`.

| Người dùng | Trước: p95 | Trước: lỗi | Sau: p95 | Sau: lỗi | Sau: p95 riêng mở lịch sử |
|---|---|---|---|---|---|
| 100 | 5494 ms | 1,13% | **1146 ms** | **0%** | 726 ms (trước 5807 ms) |
| 200 | 5631 ms | 0,79% | **1185 ms** | **0%** | 856 ms (trước 5978 ms) |
| 500 | 6597 ms | 0,02% | **1264 ms** | **0,06%** | 910 ms (trước 10 530 ms) |
| 1000 | quá tải | **15,39%** | 5965 ms | **0,02%** | |
| 2000 | quá tải | 44% | quá tải | 48% | |

**Mức chịu tải**, theo chuẩn "lỗi dưới 1% và p95 dưới 3 giây":

- Trước: **không đạt ở mức nào** (p95 đã 5,5 giây từ 100 người); nếu chỉ xét lỗi thì
  chịu được tới khoảng 500 người.
- Sau: **khoảng 500 người**; tới 1000 người vẫn gần như không lỗi nhưng p95 lên 6 giây.

## 5. Hạn chế

- Mỗi cấu hình đo 1 lần.
- Locust và server chạy chung một máy.
- Độ trễ DB là giả lập; xác nhận trên Supabase thật nằm trong thí nghiệm 05 (cách B).

## Tệp

| Tệp | Nội dung |
|---|---|
| `results/history_latency.jsonl` | Đo một request trước/sau |
| `../05_cache_aside/results/S2_a_*` | Đo tải, lịch sử chat bản cũ |
| `../05_cache_aside/results/S2_b_*` | Đo tải, lịch sử chat đã sửa |

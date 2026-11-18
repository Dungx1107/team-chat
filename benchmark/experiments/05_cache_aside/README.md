# 05 — Cache-Aside cho danh sách phòng (kèm CQRS mức nhẹ)

Ngày đo: 17–18/11/2026 · Người đo: Dat · Commit: `8fc0a74` (cache trong RAM), `732a9ea` (cache Redis)

## Tóm tắt

- **Khi người dùng chủ yếu đọc, cache hiệu quả rất lớn:** xem danh sách phòng liên tục,
  p95 ở 50 người giảm từ **~1,9 giây xuống ~0,1 giây** (gần 20 lần), và hệ thống chịu
  được 100 người thay vì kẹt hẳn.
- **Trong kịch bản dùng app sát thực tế, cache gần như không tạo khác biệt.** Chỉ **1–4%**
  request danh sách phòng được phục vụ hoàn toàn từ cache (3–5% khi chỉ 20% người chat
  chủ động): tin nhắn mới đến liên tục làm cache của phòng bị xóa, còn mỗi người chỉ mở danh sách phòng khi mở app hoặc tải lại
  trang. Danh sách phòng cũng chỉ là phần nhỏ trong tải; phần nặng là gửi tin và mở phòng.
- **Với 4 worker, cache phải nằm trên Redis.** Cache trong RAM cho kết quả sai (người
  dùng thấy dữ liệu cũ); cache Redis đúng cả 17 loại thao tác ghi. Redis sập thì app vẫn
  chạy nhờ Circuit Breaker.
- **Khi quá tải** (2000 người), có cache thì lỗi thấp hơn ở cả 3 lần so sánh, nhưng mức chênh dao động lớn (6–49 điểm %).
- Kết luận cho nhóm: Cache-Aside đúng về kiến trúc và có lợi cho tải đọc nhiều (giờ cao
  điểm mở app, khởi động lại server), nhưng **cải tiến có tác dụng lớn nhất trong thực tế
  là sửa N+1 lịch sử chat** (thí nghiệm 06).

## 1. Thiết kế

```
Đường ĐỌC   GET /api/rooms ─► CachedRoomQueries ─► ICache (RAM hoặc Redis)
                              (Cache-Aside, Decorator)    │ trượt cache
                                                          ▼
                                                      RoomQueries ─► Repository ─► DB
Đường GHI   POST/PATCH/DELETE ─► Service ─► Repository ─► DB
                                   │ phát sự kiện (đã có sẵn cho WebSocket)
                                   ▼
                           RoomCacheInvalidator ─► xóa key ─► chuyển tiếp ra WebSocket
```

| Pattern | Áp dụng |
|---|---|
| CQRS mức nhẹ | Đường đọc riêng `app/queries` cho danh sách phòng, tách khỏi Service (đường ghi). Cùng một DB |
| Cache-Aside | Đọc: có trong cache thì dùng, thiếu thì hỏi DB rồi lưu. Ghi: ghi DB rồi xóa key |
| Decorator | `CachedRoomQueries` bọc `RoomQueries`; `RoomCacheInvalidator` bọc bộ phát sự kiện |
| Observer | Xóa cache bằng chính các sự kiện Service vốn phát cho WebSocket; Service không biết có cache |
| Ports & Adapters | Cổng `ICache`, hai cài đặt `InMemoryCache` (LRU) và `RedisCache` |
| Circuit Breaker | `RedisCache` ngừng gọi Redis 5 giây sau khi lỗi |

Cache tách theo vòng đời: `user:{id}:rooms` (danh sách phòng và vai trò của một người)
và `room:{id}:summary` (tên, số thành viên, tin cuối). Một tin mới chỉ xóa đúng một key
của phòng đó. TTL 60 giây là lưới an toàn.

## 2. Kiểm tra đúng

| Kiểm tra | Kết quả |
|---|---|
| So với đường đọc cũ, 40 user × 4 kiểu phân trang × (không cache, trượt, trúng) | 480 lần, **không lệch** |
| Số truy vấn | lần đầu 4, **trúng cache 0**, người cùng nhóm vào sau 1 |
| 17 loại thao tác ghi qua HTTP (gửi/sửa/xóa tin, tệp, đổi tên phòng, thêm/xóa/đổi vai trò thành viên, biệt danh, đổi họ tên, tạo/xóa phòng, lời mời, rời phòng) | người khác tải lại thấy ngay thay đổi |
| **4 worker, cache trong RAM** | **sai**: thấy tên phòng cũ, tin cuối cũ |
| **4 worker, cache Redis** | **đúng 17/17** |
| Tắt Redis giữa chừng | request đầu 4,2 s (ngắt mạch), sau đó ~30 ms, **không lỗi**; bật lại tự dùng cache |

## 3. Điều kiện đo

| | |
|---|---|
| Máy | Laptop Windows 11, Docker Desktop; Locust chạy cùng máy (4 tiến trình) |
| Cách A | Postgres local + **giả lập độ trễ 90 ms** (`tc netem`), bằng độ trễ thật tới Supabase của nhóm ở Seoul (đo bắt tay TCP: trung vị 93 ms) |
| Cách B | Project Supabase **riêng** cùng vùng Seoul (độ trễ đo được ~98 ms), session pooler |
| Dữ liệu | Seed chung: 2000 user, 40 nhóm × 50 người × 10 phòng, 100 000 tin. Seed lại trước mỗi lượt |
| Bật/tắt cache | Cùng code, chỉ đổi `CACHE_ENABLED`; backend dựng lại trước mỗi lượt (cache rỗng) |

## 4. Kết quả

Ba mức hành vi người dùng: **chỉ đọc** (4.1, lạc quan cho cache), **người dùng thực tế**
(4.5, 20% chat chủ động), **ai cũng chat liên tục** (4.3, 4.4, bi quan). 4.2 là phép thử
phụ với ghi rất dày.

### 4.1 Chỉ đọc — cận trên (cách A, 1 worker, bể 15 kết nối)

Mỗi người xem danh sách phòng, nghỉ 1 giây, lặp lại. Trung bình 2 lần đo.

| Người dùng | Tắt cache: p95 | Bật cache: p95 | Tỉ lệ trúng cache |
|---|---|---|---|
| 50 | 1923 ms | **129 ms** | 99% |
| 100 | **kẹt hẳn** (100% lỗi) | **401 ms**, 0 lỗi | 99% |
| 200 | (đã dừng) | kẹt hẳn | |

### 4.2 Đọc + ghi dày — cận dưới (cách A, 1 worker, bể 15 kết nối)

80% xem danh sách phòng, 20% gửi tin, nghỉ 1 giây (mỗi người ~5 giây gửi một tin).

| Người dùng | Tắt cache: p95 | Bật cache: p95 | Tỉ lệ trúng cache |
|---|---|---|---|
| 50 | 2572 ms | 2202 ms | 81% |
| 100 | kẹt hẳn | gần kẹt (lỗi 10–83%) | |

### 4.3 Phiên dùng app thật (cách A, 1 worker, bể 15 kết nối)

60 giây mọi người lần lượt mở app, 240 giây chat như người thật (gửi tin ~45 s/lần,
chuyển phòng ~90 s/lần, reaction, tệp, F5 ~10 phút/lần). Lịch sử chat đã sửa N+1.

| Người dùng | Tắt cache (2 lần) | Bật cache, TTL 60 s (2 lần) | Request phục vụ hoàn toàn từ cache |
|---|---|---|---|
| 100 | p95 1298 / 1333 ms, 0 lỗi | p95 1422 / 1368 ms, 0 lỗi | 2,0% / 1,4% |
| 200 | lỗi 46% / 39% | lỗi 38% / 40% | |
| 500 | kẹt hẳn | kẹt hẳn | |

### 4.4 Phiên dùng app thật trên nền mới (cách A, 4 worker, bể 20 + 30 mỗi worker, Redis)

Sau khi merge cải tiến của Dũng. So b (đã sửa N+1, không cache) và c (thêm cache Redis):

| Người dùng | b: p95 | b: lỗi | c: p95 | c: lỗi | c: request phục vụ hoàn toàn từ cache |
|---|---|---|---|---|---|
| 100 | 1146 ms | 0% | 1142 ms | 0,15% | 3,6% |
| 200 | 1185 ms | 0% | 1156 ms | 0% | 1,1% |
| 500 | 1264 ms | 0,06% | 1353 ms | 0,03% | 1,9% |
| 1000 | 5965 ms | 0,02% | 5782 ms | 0,05% | 1,4% |
| 2000 | quá tải | 48% | quá tải | 42% | |

Riêng p95 danh sách phòng ở 100 người: 990 ms → 734 ms. Các mức khác chênh nhau trong
khoảng dao động đo.

### 4.5 Người dùng thực tế: 20% chat chủ động (cách A, 4 worker)

Như 4.4 nhưng chỉ **20%** người dùng chat chủ động (nhịp như trên); **80%** chủ yếu đọc:
vẫn mở app, chuyển phòng, F5, reaction ~3 phút/lần, ~10 phút mới gửi một tin. Ai chủ
động được chọn cố định theo user (`BENCH_ACTIVE_RATIO=0.2`). Tỉ lệ đọc:ghi theo request
HTTP tăng từ ~4:1 (4.4) lên ~5–6:1 lúc đang chat và ~10:1 tính cả đợt mở app.

Đo 2 lần (lần 2: hậu tố `_r2`).

| Người dùng | b: p95 (lần 1 / 2) | b: lỗi | c: p95 (lần 1 / 2) | c: lỗi | c: request phục vụ hoàn toàn từ cache |
|---|---|---|---|---|---|
| 100 | 1137 / 1133 ms | 0 / 0% | 1154 / 1144 ms | 0 / 0% | 4,2 / 5,9% |
| 200 | 1144 / 1132 ms | 0 / 0% | 1150 / 1147 ms | 0 / 0% | 4,8 / 5,1% |
| 500 | 1261 / 1164 ms | 0 / 0,15% | 1234 / 1289 ms | 0,01 / 0% | 4,6 / 3,7% |
| 1000 | 4933 / 8648 ms | 0 / 1,6% | 7174 \* / 60 013 ms | 0,01 \* / 8,0% | 3,0 / 4,0% |
| 2000 | quá tải | 70 / 67% | quá tải | 21 \* / 52% | |

\* Lần 1 của c ở mức 1000 và 2000 đo lại riêng (`..._rerun`, bắt đầu thẳng từ mức 1000)
vì lần chạy đầu bị gián đoạn; số liệu mức 1000/2000 trong `c_..._active0.2.json` không dùng.

- **100–500 người: hai lần đo gần như trùng nhau**, p95 ~1,1–1,3 s, gần như không lỗi, cả
  có và không có cache. Mức chịu tải theo chuẩn p95 < 3 s và lỗi < 1%: **~500 người**.
- **1000 người là mép giới hạn**: hai lần đo lệch nhau nhiều (p95 5–9 s, có lần 60 s; lỗi
  0–8%). Kết luận an toàn: chưa chịu ổn định được 1000 người.
- So với 4.4 (ai cũng chat), ghi ít đi làm hệ thống nhẹ hơn một chút nhưng **không đổi
  mức chịu tải**.
- **Cache vẫn ít tác dụng**: theo request chỉ 4–6% phục vụ hoàn toàn từ cache.
- **Khi quá tải (2000 người)**, có cache thì lỗi thấp hơn ở cả 3 lần so sánh (4.4: 42% so
  với 48%; 4.5: 21% so với 70% và 52% so với 67%), nhưng mức chênh dao động lớn nên chỉ
  nên nói cache **giảm nhẹ** lỗi khi quá tải.

### 4.6 Supabase thật (cách B)

Project Supabase **riêng** (không phải project chính), cùng vùng Seoul, session pooler,
độ trễ mạng thật ~98 ms, không giả lập. Gói miễn phí chỉ cho ~15 kết nối nên chạy
**1 worker, bể 10 + 5** -- đúng điều kiện của 4.3 để đối chiếu.

| Người dùng | Cách A tắt cache (4.3, 2 lần) | **Cách B tắt cache** | Cách A bật cache (4.3, 2 lần) | **Cách B bật cache** |
|---|---|---|---|---|
| 100 | p95 1298 / 1333 ms, 0 lỗi | **p95 1245 ms, 0 lỗi** | p95 1422 / 1368 ms, 0 lỗi | **p95 1474 ms, 0 lỗi** |
| 200 | lỗi 46% / 39% | **lỗi 42%** | lỗi 38% / 40% | **lỗi 42%** |
| 500 | kẹt hẳn | **kẹt hẳn** | kẹt hẳn | **kẹt hẳn** |

Cách B khớp cách A trong khoảng dao động giữa hai lần đo cùng cách A: **giả lập độ trễ
bằng `tc netem` đáng tin**, nên các kết quả cách A (đo được nhiều cấu hình hơn) dùng
được cho kết luận. Trên Supabase thật, request phục vụ hoàn toàn từ cache cũng chỉ 0,7%.

## 5. Vì sao cache không giúp trong kịch bản thực tế

1. **Cache bị xóa liên tục.** Mỗi nhóm 50 người gửi khoảng 1 tin/giây vào 10 phòng, nên
   mỗi phòng có tin mới khoảng 9 giây một lần, xóa `room:{id}:summary`.
2. **Danh sách phòng được đọc thưa.** Frontend chỉ gọi khi mở app, F5 hoặc khi cấu trúc
   phòng đổi (tin mới cập nhật qua WebSocket). Lần đọc sau của một người thường cách lần
   trước nhiều phút; gần như chắc chắn ít nhất một trong 10 phòng đã đổi, nên request
   vẫn phải hỏi DB (dù chỉ cho phòng đó). Tỉ lệ trúng theo key vẫn 67–75%, nhưng theo
   request chỉ 1–4%.
3. **Danh sách phòng là phần nhỏ của tải.** Phần nặng là gửi tin (~8 lượt đi về DB, mỗi
   lượt 90 ms) và mở phòng (lịch sử, tin ghim, thành viên); những phần này không cache.

## 6. Hạn chế

- Locust và server chạy cùng một máy laptop.
- Phần lớn các cấu hình đo 1–2 lần.
- Vòng 3 của lượt `A_*` (16:16–16:28 ngày 17/11) chạy trùng lúc chạy thử kịch bản session
  (seed lại DB, dựng lại backend) nên **không dùng**; `S_on600_r1` (TTL 10 phút) bị ngắt
  giữa chừng và bị thay bằng đo trên nền mới.
- Kịch bản chưa mô phỏng kết nối WebSocket (nhận tin đẩy về), tải đọc lớn nhất của app chat
  và là phần nên đo cho Redis Pub/Sub.
- Chưa đo tải tăng đột ngột và chạy dài (rò rỉ bộ nhớ, kết nối).
- Tỉ lệ trúng cache thật cần đo trên production: `/health` có sẵn `hit_rate` và `full_hit_rate`.

## 7. Phát hiện cho nhóm

- **Bể kết nối 4 × (20 + 30) = 200 kết nối vượt giới hạn Supabase gói miễn phí**
  (~15 kết nối qua session pooler). Trên production thật, tải cao sẽ bị Supabase từ chối
  kết nối thay vì xếp hàng. Kích thước bể giờ chỉnh được qua `DB_POOL_SIZE`,
  `DB_MAX_OVERFLOW`; cần chọn theo gói Supabase (hoặc dùng transaction pooler, cổng 6543).
- Nút thắt tiếp theo: số lượt đi về DB khi **gửi tin** (~8) nhân với độ trễ tới DB.

## Chạy lại

```bash
bash benchmark/experiments/05_cache_aside/run_all.sh       # 4.1, 4.2
bash benchmark/experiments/05_cache_aside/run_session.sh   # 4.4 (CONFIGS để chọn cấu hình)
ACTIVE_RATIO=0.2 bash benchmark/experiments/05_cache_aside/run_session.sh   # 4.5
bash benchmark/experiments/05_cache_aside/run_supabase.sh  # 4.6, cần BENCH_DATABASE_URL trong .env
```

## Tệp kết quả (`results/`)

| Tiền tố | Lượt |
|---|---|
| `A_rooms_*`, `A_rooms_mixed_*` | 4.1, 4.2 (dùng r1, r2) |
| `S_off_*`, `S_on60_*` | 4.3 |
| `S2_a_*`, `S2_b_*`, `S2_c_*` (không có `_active`) | 4.4 (a = lịch sử chat bản cũ, xem thí nghiệm 06) |
| `S2_*_active0.2*` | 4.5 lần 1 (`c_..._active0.2` mức 1000/2000 không dùng; dùng `_rerun`), `_r2` là lần 2 |
| `B_supabase_*` | 4.6 |

Mỗi lượt có `.json` (số liệu), `_console.txt`, `_resources.csv` (CPU/RAM mỗi 5 giây),
`_backend.log.gz`.

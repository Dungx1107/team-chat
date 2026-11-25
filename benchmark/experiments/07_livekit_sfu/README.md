# 07 — Cuộc gọi nhóm: mesh P2P → LiveKit SFU

Cải tiến của Nhân (nhánh `Nhan`, commit `337887e`): cuộc gọi **nhóm** chuyển từ mesh P2P
sang **LiveKit SFU tự host** (`livekit-server 1.13.11`, một node). Gọi 1-1 vẫn P2P.
Trình duyệt bật simulcast, adaptiveStream, dynacast.

Thư mục này là khung đo cho cải tiến đó. Bản đo trước của Nhân (Kaggle, trình duyệt
thật, server và người dùng giả chung 4 lõi) đã cho thấy upload mỗi người giảm 67–86%,
nhưng mức 24×4 hỏng vì **máy đo hết CPU** (fps mã hóa phía gửi tụt còn 11), nên chưa
nói được sức chịu của server.

## Nguyên tắc

1. **Server không tranh CPU với người dùng giả.** Ghim lõi: LiveKit một nhóm lõi, bot
   nhóm còn lại. Mỗi mức đều ghi CPU nhóm lõi của bot; vượt 85% thì mức đó bị đánh dấu
   không hợp lệ.
2. **Người dùng giả là bot nhẹ** (`lk load-test`): gửi video đã mã hóa sẵn có simulcast,
   nhận mà không giải mã. Rẻ hơn trình duyệt hàng chục lần.
3. **Không cần đẩy tới chỗ sập.** Đo tài nguyên ở nhiều mức, khớp đường thẳng
   *CPU server theo số luồng chuyển tiếp*, rồi suy ra sức chịu cho số lõi bất kỳ
   (mục "Đánh giá bằng tài nguyên").

## Bộ kịch bản

| | Câu hỏi | Cách đo | Công cụ | Trạng thái |
|---|---|---|---|---|
| **K0** | Máy tạo tải nuôi được bao nhiêu bot? | Cột "CPU bot" của mọi lần chạy | `sfu_load.py` | có sẵn |
| **K1** | Người dùng được lợi gì so với mesh? | 1 cuộc N = 2, 4, 6, 8 người, Chrome thật: upload, download, CPU trình duyệt, thời gian thấy hình | Chrome + `chrome://webrtc-internals` | bổ sung vào bảng cũ của Nhân |
| **K2a** | Nối tiếp bảng cũ: k cuộc × 4 người | `--scenario uniform`, k = 2 … 48 | `sfu_load.py` | có sẵn |
| **K2b** | Sức chịu với tải giống thật | `--scenario mixed`, 10 → 80 cuộc, cỡ cuộc trộn lẫn | `sfu_load.py` | có sẵn |
| **K3** | Một cuộc gọi tối đa bao nhiêu người? | `--scenario large`, 1 cuộc N = 16 … 100, 4 người bật camera | `sfu_load.py` | có sẵn |
| **K4** | Backend có nghẽn khi nhiều người cùng vào gọi? Reconciler theo kịp không? | Locust: `group → join → sfu-session` dồn trong 60 s; giữ X cuộc mở và đo một vòng đối soát | Locust | chưa viết |
| **K5** | Gọi video có làm chậm chat? | Chat `session` 500 người (thí nghiệm 05) chạy cùng K2b | Locust + `sfu_load.py` | chưa viết |
| **K6** | LiveKit sập 30 s thì sao? | Tắt LiveKit giữa cuộc gọi: backend trả 503 nhanh không, client tự nối lại không | thủ công | tùy chọn |

### Mô hình tải K2b (công ty ~2000 người)

- Lúc cao điểm khoảng 100–150 người đang trong cuộc gọi **nhóm**, khoảng 30–40 cuộc.
  Thang đo 10 → 80 cuộc phủ từ mức thường tới gấp đôi cao điểm.
- Cỡ cuộc gọi: 60% có 3–4 người, 30% có 5–8 người, 10% có 10–16 người.
- 60% người bật camera (`--camera-ratio`), mọi người bật micro (`--mic-ratio 1`, bi quan).
- Video `medium` (360p, hợp với ô lưới nhỏ của app), simulcast bật như frontend.
- Hạt giống ngẫu nhiên cố định: lần chạy nào cũng ra cùng danh sách cuộc gọi.

Đây là giả định của nhóm, ghi rõ trong báo cáo. Đổi bằng tham số nếu nhóm chốt số khác.

### Một cuộc gọi được mô phỏng thế nào

Cuộc gọi N người, c bật camera, a bật micro = c bot phát video + a bot phát âm thanh +
(N − 1) bot nhận. SFU phải chuyển tiếp **đúng bằng cuộc gọi thật**: c(N−1) luồng video,
a(N−1) luồng âm thanh. Số kết nối thì nhiều hơn thật (c + a + N − 1 so với N), nên kết
quả hơi bi quan.

### Tiêu chí đạt mỗi mức

- mọi cuộc gọi kết nối được, nhận ≥ 99% số luồng dự kiến
- mất gói phía người nhận ≤ 2%
- CPU nhóm lõi của LiveKit ≤ 80%
- CPU nhóm lõi của bot ≤ 85% (không thì mức đó không hợp lệ, không phải lỗi của server)

## Chạy

### Trên Kaggle (4 lõi: LiveKit lõi 0-1, bot lõi 2-3)

Bật Internet trong Settings của notebook, rồi:

```python
!git clone --depth 1 -b Dat https://github.com/Dungx1107/team-chat.git
%cd team-chat/benchmark/experiments/07_livekit_sfu
!nproc; free -g

# K2a: nối tiếp bảng cũ (k cuộc x 4 người)        ~35 phút
!python sfu_load.py --scenario uniform --steps "2 4 8 16 24 32 48"
# K2b: tải giống thật                               ~25 phút
!python sfu_load.py --scenario mixed --steps "10 20 40 60 80"
# K3: phòng lớn                                     ~20 phút
!python sfu_load.py --scenario large --steps "16 32 50 100"

!zip -qr /kaggle/working/sfu_results.zip results
```

Tải `sfu_results.zip` ở tab Output, giải nén vào `results/` của thư mục này.

- Script tự tải `livekit-server` và `lk` vào `bin/`, không cần Docker.
- Mặc định mỗi mức đo 180 s và **dừng ở mức đầu tiên không đạt**. Muốn đo tiếp thì
  thêm `--keep-going`.
- In lại bảng bất cứ lúc nào: `python summarize.py results/<tệp>.json`.

### Trên máy có Docker (thử nhanh)

```bash
cd benchmark/experiments/07_livekit_sfu
MSYS_NO_PATHCONV=1 docker run --rm --cpuset-cpus=0-3 -v "$PWD:/w" -w /w python:3.12-slim \
  sh -c "pip install -q psutil; python sfu_load.py --scenario uniform --steps '2 6' --seconds 30 --server-cpus 0,1 --bot-cpus 2,3"
```

## Số đo

Mỗi mức tải ghi vào `results/<kịch bản>_<thời gian>.json`:

| Nhóm | Trường |
|---|---|
| Tải | `calls`, `participants`, `cameras`, `video_streams_forwarded`, `audio_streams_forwarded`, `call_sizes` |
| Chất lượng phía người nhận (bot) | `tracks_received / tracks_expected`, `subscriber_loss_pct`, `subscriber_kbps_avg`, `bot_errors` |
| Tài nguyên LiveKit | `server_cpu` (số lõi, trung bình và đỉnh), `server_cores_util` (% nhóm lõi), `server_rss_mb`, `server_in_mbps`, `server_out_mbps` |
| Kết nối | `calls_connected`, `connect_seconds`, `join_latency_ms` (của LiveKit) |
| Máy tạo tải | `bots_cpu`, `bot_cores_util` |

Kèm theo: `*_timeline.json` (mẫu CPU/RAM mỗi 2 s) và `*_logs/` (log LiveKit, kết quả
từng bot).

## Đánh giá bằng tài nguyên

Khi không đo được tới giới hạn thật (máy đo nhỏ), `summarize.py` dùng các mức hợp lệ để
khớp:

    CPU server (lõi) ≈ a + b × (số luồng video chuyển tiếp)

rồi in:

- **chi phí đơn vị**: số lõi cho mỗi 100 luồng, Mbps mỗi luồng, MB RAM mỗi người
- **suy ra**: với 1, 2, 4, 8 lõi (giữ CPU ≤ 80%) thì chịu được bao nhiêu luồng / cuộc gọi
- **R²**: gần 1 nghĩa là tải tăng tuyến tính, phép suy ra đáng tin. Nên có ít nhất 4 mức hợp lệ.

Hai giới hạn cần nêu trong báo cáo:

1. Bot và LiveKit nói chuyện qua `localhost`: không có độ trễ, mất gói hay giới hạn băng
   thông của mạng thật. Kết quả là sức chịu **CPU**. Giới hạn **mạng** thì tính từ
   `server_out_mbps`: ví dụ 0,6 Mbps mỗi luồng × 500 luồng = 300 Mbps cổng ra.
2. Bot không giải mã video, nên không đo được trải nghiệm hình ảnh. Phần đó lấy từ K1
   (Chrome thật, ít người).

## So với mesh

Server của mesh chỉ chuyển tín hiệu, gần như không tốn tài nguyên media, nên **không so
CPU server giữa mesh và SFU**. So sánh công bằng là:

- phía người dùng (K1 và bảng cũ của Nhân): upload mỗi người mesh = (N−1) × bitrate, SFU = 1 luồng (vài lớp simulcast)
- chi phí đổi lại: SFU cần X lõi và Y Mbps cổng ra cho mỗi 100 luồng (K2)

Chạy thử nhỏ trên laptop (Docker, LiveKit 2 lõi, 8 cuộc / 33 người) thấy khoảng 0,6 lõi
cho mỗi 100 luồng video, 0,6 Mbps mỗi luồng. Chỉ để kiểm tra script, **không dùng làm
kết quả**.

# Hướng dẫn gọi xuyên mạng bằng máy cá nhân làm máy chủ

Tài liệu này hướng dẫn chạy Team Chat trên máy của bạn, sau đó cho người khác
truy cập từ mạng Wi-Fi/4G khác và thực hiện cuộc gọi thoại/video.

## 1. Mô hình hoạt động

Máy của bạn chạy các thành phần sau:

- **Team Chat + Nginx**: phục vụ giao diện, API và WebSocket signaling.
- **Cloudflare Tunnel**: tạo một địa chỉ HTTPS công khai trỏ về máy của bạn.
- **TURN server** (khuyến nghị): chuyển tiếp media WebRTC khi hai người dùng ở
  sau NAT nghiêm ngặt, mạng trường học hoặc mạng công ty.

Cloudflare Tunnel chỉ chuyển tiếp website, API và WebSocket. Nó **không tự
chuyển tiếp media WebRTC**. Vì vậy website có thể mở được nhưng cuộc gọi vẫn
“đang kết nối” nếu không có TURN.

## 2. Yêu cầu

Trên máy làm máy chủ:

- Docker Desktop đang chạy.
- Mã nguồn Team Chat và file `.env` đã được cấu hình.
- Kết nối Internet ổn định.
- Cài `cloudflared` theo hướng dẫn chính thức:
  [Cloudflare Tunnel documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)

Trên máy người gọi:

- Trình duyệt hiện đại có hỗ trợ WebRTC.
- Cho phép trình duyệt dùng microphone và camera.
- Có thể truy cập địa chỉ HTTPS do Cloudflare cung cấp.

Không cần mở port 80/443 trên router khi dùng Quick Tunnel. Cloudflared tạo
kết nối outbound từ máy chủ đến Cloudflare.

## 3. Khởi động Team Chat trên máy chủ

Mở Terminal/PowerShell tại thư mục dự án:

```bash
cd <thu-muc-team-chat>
docker compose up -d --build
docker compose ps
```

Các service `db`, `backend` và `web` phải ở trạng thái đang chạy. Nếu đây là
lần đầu chạy dự án, hãy tạo dữ liệu mẫu theo [RUN_GUIDE.md](../RUN_GUIDE.md).

Kiểm tra đường dẫn nội bộ trước khi tạo tunnel:

```bash
curl http://localhost:8080/health
```

Nếu lệnh trả về lỗi, xem log:

```bash
docker compose logs --tail=100 web backend
```

Port `8080` là port nội bộ dành cho tunnel và chỉ bind trên `127.0.0.1`.
Không đổi tunnel sang port database hoặc port backend `8000`.

## 4. Tạo địa chỉ truy cập từ Internet

Giữ Docker đang chạy, sau đó mở **Terminal thứ hai**:

```bash
cloudflared tunnel --url http://localhost:8080
```

Trong output sẽ có một URL dạng:

```text
https://ten-ngau-nhien.trycloudflare.com
```

Giữ cửa sổ này mở trong suốt thời gian demo. Nếu đóng tiến trình
`cloudflared`, địa chỉ sẽ ngừng hoạt động.

Trên máy người dùng, mở chính xác URL `https://...trycloudflare.com` đó. Không
dùng `https://localhost`, `http://localhost:8080` hoặc địa chỉ `127.0.0.1` vì
những địa chỉ này trỏ về máy của người dùng, không phải máy chủ.

Đăng nhập bằng tài khoản đã có, vào cùng một phòng chat rồi bắt đầu cuộc gọi.
Nếu dùng Google Login, origin mới phải được thêm vào **Authorized JavaScript
origins** của Google OAuth Client. Quick Tunnel tạo URL mới mỗi lần chạy nên
đây là hạn chế của cách dùng tạm thời.

## 5. Cấu hình TURN để gọi ổn định qua Internet

### Cách khuyến nghị: dùng TURN bên ngoài

Đăng ký một nhà cung cấp TURN, sau đó mở `.env` trên máy chủ và đặt
`ICE_SERVERS` trên **một dòng**, thay placeholder bằng thông tin thật của bạn:

```ini
ICE_SERVERS=[{"urls":"stun:stun.relay.metered.ca:80"},{"urls":"turn:global.relay.metered.ca:80","username":"<TURN_USERNAME>","credential":"<TURN_PASSWORD>"},{"urls":"turn:global.relay.metered.ca:443","username":"<TURN_USERNAME>","credential":"<TURN_PASSWORD>"},{"urls":"turns:global.relay.metered.ca:443?transport=tcp","username":"<TURN_USERNAME>","credential":"<TURN_PASSWORD>"}]
```

Không đưa username/password TURN thật vào Git, ảnh chụp màn hình hoặc tài liệu
chia sẻ. Sau khi sửa `.env`, khởi động lại backend:

```bash
docker compose up -d --build backend
docker compose exec backend python check_turn.py
```

Kết quả cần cho thấy TURN phản hồi bình thường. Nếu dùng `turns:` qua TLS,
script có thể ghi chú rằng chưa kiểm tra được TLS; hãy kiểm tra bằng một cuộc
gọi thật.

### Cách tự host TURN trên chính máy chủ

Compose có sẵn service coturn tùy chọn. Cách này chỉ phù hợp khi bạn kiểm soát
router và firewall:

1. Xác định IP LAN của máy chủ, ví dụ `192.168.1.10`.
2. Đặt trong `.env`:

   ```ini
   TURN_EXTERNAL_IP=192.168.1.10
   TURN_USER=ten-nguoi-dung
   TURN_PASSWORD=mat-khau-dai-va-ngau-nhien
   ```

3. Trên router, chuyển tiếp đến máy chủ:
   - UDP/TCP `3478`
   - UDP `50000-50010`
4. Mở các cổng tương ứng trong firewall của máy chủ.
5. Khởi động TURN:

   ```bash
   docker compose --profile turn up -d
   ```

`TURN_EXTERNAL_IP` phải là địa chỉ có thể được máy khách bên ngoài truy cập.
Không dùng `127.0.0.1`, `localhost` hoặc chỉ dùng IP LAN nếu người gọi đang ở
ngoài router. Khi tự host TURN qua Internet, cần dùng IP public hoặc DNS trỏ
đến IP public và cấu hình ICE server tương ứng.

## 6. Kiểm thử đường truyền WebRTC

Mở URL công khai, đăng nhập trên hai thiết bị thuộc hai mạng khác nhau, rồi
thử cuộc gọi. Có thể ép trình duyệt chỉ dùng TURN bằng cách thêm `?relay=1`
vào URL:

```text
https://ten-ngau-nhien.trycloudflare.com/?relay=1
```

- Gọi được với `?relay=1`: TURN hoạt động.
- Chỉ gọi được khi bỏ `?relay=1`: kết nối trực tiếp hoạt động, nhưng TURN có
  thể chưa đúng hoặc chưa cần dùng.
- Không gọi được ở cả hai chế độ: kiểm tra quyền camera/microphone, WebSocket,
  log backend và cấu hình ICE server.

Chế độ `?relay=1` làm tăng độ trễ và tiêu tốn băng thông TURN, chỉ nên dùng để
kiểm thử hoặc khi cần buộc media đi qua relay.

## 7. Xử lý sự cố nhanh

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| URL tunnel không mở | Kiểm tra `docker compose ps`, sau đó thử `curl http://localhost:8080/health`. |
| Trang mở nhưng đăng nhập lỗi | Kiểm tra browser DevTools, `.env` và log `backend`; nếu dùng Google Login, thêm origin tunnel vào OAuth. |
| Người kia không nhận được cuộc gọi | Không đóng `cloudflared`; kiểm tra WebSocket và dùng đúng URL `https://`. |
| Có chuông nhưng không có tiếng/hình | Cho phép camera/micro; chạy `docker compose exec backend python check_turn.py` và thử `?relay=1`. |
| Gọi được cùng Wi-Fi nhưng không được qua 4G | Thêm TURN công khai hoặc tự host TURN với port forwarding. |
| Chứng chỉ bị báo không an toàn | Người dùng đang mở URL nội bộ/self-signed thay vì URL HTTPS của Cloudflare. |
| Tunnel bị ngắt | Khởi động lại `cloudflared`; Quick Tunnel có URL tạm thời và không phù hợp chạy lâu dài. |

Xem thêm:

- [10-call-features.md](10-call-features.md) — kiến trúc WebRTC và giới hạn
  gọi nhóm.
- [12-deployment.md](12-deployment.md) — topology Docker và các port.
- [RUN_GUIDE.md](../RUN_GUIDE.md) — cài đặt và chạy dự án lần đầu.

## 8. Checklist trước khi gửi link cho người khác

- [ ] `docker compose ps` cho thấy `db`, `backend`, `web` đang chạy.
- [ ] `curl http://localhost:8080/health` trả về thành công.
- [ ] Tiến trình `cloudflared` vẫn đang chạy.
- [ ] Đã gửi URL `https://...trycloudflare.com`, không gửi `localhost`.
- [ ] Đã cấu hình TURN nếu người gọi ở mạng 4G, mạng trường học hoặc mạng
      công ty.
- [ ] Đã thử một cuộc gọi thật và cấp quyền camera/microphone.
- [ ] Khi kết thúc demo, dừng tunnel bằng `Ctrl+C`.


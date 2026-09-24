# HƯỚNG DẪN CHẠY HỆ THỐNG TEAM CHAT

Tài liệu dành cho thành viên trong nhóm: clone về là chạy được, không cần biết trước gì về dự án.

---

## MỤC LỤC

1. [Chạy lần đầu](#1-chạy-lần-đầu)
2. [Tài khoản dùng thử](#2-tài-khoản-dùng-thử)
3. [Các lần sau](#3-các-lần-sau)
4. [Thử từng tính năng](#4-thử-từng-tính-năng)
5. [Thử trên điện thoại và máy khác](#5-thử-trên-điện-thoại-và-máy-khác)
6. [Lệnh bảo trì](#6-lệnh-bảo-trì)
7. [Xử lý sự cố](#7-xử-lý-sự-cố)
8. [Checklist trước khi demo](#8-checklist-trước-khi-demo)
9. [Phụ lục: chạy không cần nginx](#9-phụ-lục-chạy-không-cần-nginx)

---

# 1. CHẠY LẦN ĐẦU

## Cần cài sẵn

Chỉ cần **Docker Desktop**. Không cần cài Python, Node hay PostgreSQL — mọi thứ chạy trong container.

Trên Windows, Docker Desktop đòi hỏi **WSL2**. Nếu chưa có, mở PowerShell **quyền Administrator**:

```powershell
wsl --install
```

rồi khởi động lại máy.

## Bước 1: Lấy mã nguồn

```bash
git clone https://github.com/Dungx1107/team-chat.git
cd team-chat
```

## Bước 2: Tạo file `.env`

**Đây là bước hay bị quên nhất.** File `.env` chứa mật khẩu nên không được đẩy lên Git, mỗi người phải tự tạo. Thiếu nó thì `docker compose` báo lỗi biến rỗng.

Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Sau đó mở `.env` và sửa **hai dòng**:

```ini
POSTGRES_PASSWORD=dat-mot-mat-khau-bat-ky
DATABASE_URL=postgresql://postgres:dat-mot-mat-khau-bat-ky@db:5432/teamchat_db
```

Mật khẩu ở hai dòng phải **giống hệt nhau**. Nên sửa thêm `JWT_SECRET_KEY` thành một chuỗi ngẫu nhiên dài trên 32 ký tự.

## Bước 3: Khởi động

Mở Docker Desktop trước, chờ icon cá voi ở khay hệ thống ngừng nhấp nháy. Rồi:

```bash
docker compose up -d --build
```

Lần đầu mất khoảng 2–5 phút vì phải tải image và build. Kiểm tra:

```bash
docker compose ps
```

Cả ba service `db`, `backend`, `web` phải ở trạng thái `Up`, riêng `db` phải `(healthy)`.

## Bước 4: Nạp dữ liệu mẫu

```bash
docker compose exec backend python seed_users.py
```

Lệnh này tạo 4 tài khoản, một phòng công khai và một phòng riêng tư.

## Bước 5: Mở trình duyệt

```
https://localhost
```

Lần đầu trình duyệt báo **"Kết nối của bạn không phải là kết nối riêng tư"**. Đây là bình thường: hệ thống dùng chứng chỉ tự ký. Bấm **Nâng cao → Tiếp tục truy cập localhost**. Mỗi thiết bị chỉ phải làm một lần.

> **Vì sao phải HTTPS?** Trình duyệt chỉ cho phép dùng micro và camera trên kết nối bảo mật. Không có HTTPS thì tính năng gọi điện không chạy.

---

# 2. TÀI KHOẢN DÙNG THỬ

Mật khẩu chung: **`password123`**

| Email | Tên | Vai trò trong `# Phòng Kiến Trúc` |
| --- | --- | --- |
| `user1@example.com` | Nguyễn Xuân Dũng | **Chủ phòng** — đủ mọi quyền |
| `user2@example.com` | Trần Văn Nam | **Quản trị viên** — xóa tin người khác, thêm/xóa thành viên |
| `user3@example.com` | Lê Hoàng Anh | Thành viên thường |
| `user4@example.com` | Phạm Phương Mai | **Chưa vào phòng nào** — để thử mời thành viên |

Ngoài ra có phòng riêng tư `🔒 Nhóm Trưởng`, chỉ `user1` và `user2` nhìn thấy.

---

# 3. CÁC LẦN SAU

```bash
# 1. Mở Docker Desktop, chờ khởi động xong
# 2. Chạy:
cd <thư-mục-team-chat>
docker compose up -d
```

Rồi vào `https://localhost`. **Không cần seed lại**, dữ liệu nằm trong Docker volume.

Docker Desktop không tự bật cùng Windows, nên phải mở thủ công trước.

## Khi kéo code mới về

```bash
git pull
docker compose up -d --build
```

Nếu người khác vừa thêm **cột mới vào database**, backend sẽ báo lỗi kiểu `column ... does not exist`. Dự án dùng `create_all()` — chỉ tạo bảng chưa có, không tự thêm cột vào bảng đã tồn tại. Cách xử lý nhanh nhất:

```bash
docker compose down -v
docker compose up -d
docker compose exec backend python seed_users.py
```

> ⚠️ `down -v` xóa sạch tin nhắn và tệp đã tải lên. Hiện chỉ là dữ liệu thử nên không sao.

---

# 4. THỬ TỪNG TÍNH NĂNG

Muốn thấy realtime thì phải mở **nhiều cửa sổ** và đăng nhập tài khoản khác nhau:

- Cửa sổ thường + cửa sổ ẩn danh (`Ctrl + Shift + N`)
- Hoặc dùng thêm một trình duyệt khác

## Chat

| Thử gì | Cách làm |
| --- | --- |
| Tin nhắn realtime | Gõ ở cửa sổ này, cửa sổ kia hiện ngay, không cần F5 |
| Đang soạn tin | Gõ mà chưa gửi, bên kia thấy "đang soạn tin..." |
| Biểu cảm | Rê chuột lên tin nhắn, chọn emoji. Bấm lại để gỡ |
| Gửi tệp | Nút 📎. Ảnh và video hiện ngay trong khung chat, tối đa 25MB |
| Trả lời, ghim, sửa, xóa | Các nút hiện khi rê chuột lên tin nhắn |

## Phân quyền

Đăng nhập `user2` (quản trị viên) rồi thử **xóa phòng** — bị chặn, chỉ chủ phòng mới xóa được.

Đăng nhập `user1` (chủ phòng), mở panel **👥**, bấm `⋯` cạnh tên ai đó để phong quản trị hoặc xóa khỏi phòng.

## Phòng riêng tư

Đăng nhập `user4` — sẽ **không thấy** phòng `🔒 Nhóm Trưởng` trong danh sách. Từ `user1` mời `user4` vào phòng đó, phòng sẽ hiện ra ngay ở cửa sổ của `user4`.

## Gọi 1-1

1. Mở panel **👥**
2. Rê chuột lên tên một người **đang online**
3. Bấm **📞** (thoại) hoặc **🎥** (video)
4. Cửa sổ kia đổ chuông, bấm nút xanh để nghe

Người nhận có 30 giây để nghe, quá thì tính là cuộc gọi nhỡ.

## Gọi nhóm

1. Bấm **🎥 Gọi nhóm** trên thanh tiêu đề phòng
2. Các cửa sổ khác hiện dải xanh *"Cuộc gọi nhóm đang diễn ra"* kèm nút **Tham gia**
3. Lưới video tự giãn theo số người
4. Một người rời đi thì những người còn lại vẫn nói chuyện tiếp

Tối đa **6 người** (mô hình mesh: mỗi máy nối trực tiếp tới từng người còn lại).

> **Lưu ý về camera:** máy thường chỉ có một webcam. Nhiều tab trong **cùng một trình duyệt** dùng chung được, nhưng **hai trình duyệt khác nhau** thì cái mở sau báo lỗi `Device in use`. Khi đó app tự chuyển người đó sang chế độ chỉ có tiếng — cuộc gọi vẫn chạy. Nhớ tắt Zoom, Teams hoặc tab nào đang dùng camera.

## Tài liệu API

```
https://localhost/docs
```

Giao diện Swagger, bấm "Try it out" để gọi thử API ngay trên trình duyệt.

---

# 5. THỬ TRÊN ĐIỆN THOẠI VÀ MÁY KHÁC

Tất cả thiết bị phải **cùng một mạng Wi-Fi** với máy chạy server. Không có Wi-Fi chung thì bật điểm phát sóng trên điện thoại rồi cho laptop kết nối vào.

## Bước 1: Lấy IP của máy chạy server

Windows:

```powershell
ipconfig
```

Tìm dòng `IPv4 Address` của card Wi-Fi, ví dụ `192.168.1.18`. Bỏ qua các IP `192.168.56.x` (card ảo VirtualBox).

Linux/macOS:

```bash
hostname -I | awk '{print $1}'
```

## Bước 2: Ghi IP vào `.env`

```ini
CERT_IPS=192.168.1.18
```

Rồi tạo lại chứng chỉ cho khớp IP mới:

```bash
docker compose down
docker volume rm team-chat_certs
docker compose up -d
```

> Tên volume lấy theo tên thư mục dự án. Nếu bạn clone vào thư mục tên khác, chạy `docker volume ls` để xem tên đúng (dạng `<tên-thư-mục>_certs`).

Bỏ qua bước này vẫn vào được, chỉ là trình duyệt cảnh báo thêm một dòng "tên không khớp".

## Bước 3: Truy cập từ thiết bị khác

```
https://192.168.1.18
```

Bấm **Nâng cao → Tiếp tục**. Trên iPhone, Safari hiện "Chi tiết → Truy cập trang web này".

## Không gọi được qua Internet

Hiện tại chỉ gọi được trong cùng mạng LAN. Gọi qua Internet cần thêm máy chủ **TURN** và một tunnel để đưa server ra ngoài — chưa làm.

---

# 6. LỆNH BẢO TRÌ

| Việc | Lệnh |
| --- | --- |
| Xem trạng thái | `docker compose ps` |
| Xem log backend | `docker compose logs -f backend` |
| Xem log tất cả | `docker compose logs -f` |
| Khởi động lại backend | `docker compose restart backend` |
| Dừng (giữ dữ liệu) | `docker compose down` |
| Bật lại | `docker compose up -d` |
| Build lại sau khi sửa code | `docker compose up -d --build` |
| Xem dữ liệu trong DB | `docker compose exec db psql -U postgres -d teamchat_db` |

Sửa code Python trong `backend/` thì chỉ cần `docker compose restart backend`, không phải build lại (thư mục được mount vào container).

Sửa file trong `frontend/` thì **không cần làm gì cả** — chỉ cần `Ctrl + F5` trên trình duyệt.

## Reset toàn bộ dữ liệu

```bash
docker compose down -v
docker compose up -d
docker compose exec backend python seed_users.py
```

---

# 7. XỬ LÝ SỰ CỐ

## `docker compose` báo lỗi 500 hoặc "daemon is not running"

Mở Docker Desktop và chờ khởi động xong. Nếu đã mở mà vẫn lỗi, nhiều khả năng **tính năng ảo hóa của Windows bị tắt** (do bản cập nhật Windows hoặc phần mềm chống gian lận của game). Kiểm tra:

```powershell
wsl -d docker-desktop -e echo ok
```

Báo `HCS_E_SERVICE_NOT_AVAILABLE` thì mở PowerShell **quyền Administrator**:

```powershell
dism /online /enable-feature /featurename:VirtualMachinePlatform /all
dism /online /enable-feature /featurename:HypervisorPlatform /all
```

Rồi **Restart** máy (chọn Restart chứ không phải Shut down).

## Trang không mở được / cổng 443 bị chiếm

Kiểm tra:

```powershell
Get-NetTCPConnection -LocalPort 443 -State Listen
```

Bị chiếm thì đổi cổng trong `.env`:

```ini
HTTPS_PORT=8443
HTTP_PORT=8080
```

rồi `docker compose up -d`, và vào `https://localhost:8443`.

## Bấm gửi tin nhắn mà không có gì xảy ra

Phiên đăng nhập đã hết hạn. Tải lại trang bằng `Ctrl + F5` rồi đăng nhập lại.

## Backend báo `column ... does not exist`

Có người thêm cột mới vào database. Xem lại [mục 3](#khi-kéo-code-mới-về).

## Không bật được camera khi gọi

Xem lưu ý ở [mục 4](#gọi-nhóm). Tắt các ứng dụng khác đang dùng camera, hoặc dùng cùng một trình duyệt cho các cửa sổ test.

## Giao diện cũ, không thấy tính năng mới

Trình duyệt dùng lại file JS trong cache. Nhấn `Ctrl + F5` (Windows) hoặc `Cmd + Shift + R` (macOS).

---

# 8. CHECKLIST TRƯỚC KHI DEMO

**Chuẩn bị**

- [ ] Docker Desktop đang chạy
- [ ] `docker compose ps` — cả ba service `Up`, `db` là `healthy`
- [ ] Đã seed dữ liệu, đăng nhập được `user1@example.com`
- [ ] Đã bấm "Tiếp tục" qua cảnh báo chứng chỉ trên **mọi** máy sẽ dùng để demo
- [ ] Tắt Zoom, Teams, và các tab đang chiếm camera

**Thử trước khi lên demo**

- [ ] Gửi tin nhắn giữa hai cửa sổ, tin hiện ngay không cần F5
- [ ] Gửi một ảnh, ảnh hiện trong khung chat
- [ ] Thả biểu cảm, cửa sổ kia thấy ngay
- [ ] Gọi 1-1: đổ chuông, nghe máy, thấy hình và nghe tiếng
- [ ] Gọi nhóm: người thứ ba bấm Tham gia, lưới thành 3 ô
- [ ] Mở `https://localhost/docs` xem Swagger có lên không

**Nếu demo nhiều thiết bị**

- [ ] Tất cả cùng một Wi-Fi
- [ ] `CERT_IPS` trong `.env` khớp IP hiện tại
- [ ] Điện thoại vào được `https://<IP>` và đăng nhập được

---

# 9. PHỤ LỤC: CHẠY KHÔNG CẦN NGINX

Cách cũ, giữ lại để tham khảo. Cần cài sẵn Python trên máy.

```bash
# Cửa sổ 1 - backend + database
docker compose up -d db backend

# Cửa sổ 2 - frontend, phải giữ mở
cd frontend
python -m http.server 3000 --bind 0.0.0.0
```

Rồi vào `http://localhost:3000`.

> **Cách này không gọi điện được** khi truy cập bằng địa chỉ IP, vì chạy trên HTTP nên trình duyệt chặn micro và camera. Vào bằng `localhost` thì gọi được, vì trình duyệt coi `localhost` là an toàn.

Frontend tự nhận biết: chạy ở cổng 3000 thì gọi thẳng backend ở cổng 8000, chạy sau nginx thì dùng chung địa chỉ với trang.

---

# TÓM TẮT

Chạy lần đầu:

```bash
git clone https://github.com/Dungx1107/team-chat.git
cd team-chat
cp .env.example .env          # rồi sửa POSTGRES_PASSWORD và DATABASE_URL
docker compose up -d --build
docker compose exec backend python seed_users.py
```

Các lần sau: mở Docker Desktop → `docker compose up -d` → vào `https://localhost`.

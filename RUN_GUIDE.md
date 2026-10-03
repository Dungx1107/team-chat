# HƯỚNG DẪN CHẠY HỆ THỐNG TEAM CHAT

Tài liệu dành cho thành viên trong nhóm: clone về là chạy được, không cần biết trước gì về dự án.

---

## MỤC LỤC

1. [Chọn trường hợp của bạn](#1-chọn-trường-hợp-của-bạn)
2. [Chạy lần đầu cho người mới](#2-chạy-lần-đầu-cho-người-mới)
3. [Cấu hình Đăng nhập bằng Google](#3-cấu-hình-đăng-nhập-bằng-google)
4. [Tài khoản dùng thử](#4-tài-khoản-dùng-thử)
5. [Các lần sau](#5-các-lần-sau)
6. [Thử từng tính năng](#6-thử-từng-tính-năng)
7. [Thử trên điện thoại và máy khác](#7-thử-trên-điện-thoại-và-máy-khác)
6B. [Gọi qua Internet](#6b-gọi-qua-internet-khác-mạng)
8. [Lệnh bảo trì](#8-lệnh-bảo-trì)
9. [Xử lý sự cố](#9-xử-lý-sự-cố)
10. [Checklist trước khi demo](#10-checklist-trước-khi-demo)
11. [Phụ lục: chạy không cần nginx](#11-phụ-lục-chạy-không-cần-nginx)

## Lệnh nhanh nhất cho người đã có cấu hình

Nếu bạn đã có file `.env`, Docker volume và cấu hình từ trước, **không chạy lại `cp .env.example .env` và không chạy `seed_users.py`**:

```bash
cd <thư-mục-team-chat>
docker compose up -d --build
```

Sau đó mở `https://localhost`.

---

# 1. CHỌN TRƯỜNG HỢP CỦA BẠN

| Trường hợp | Cần làm |
| --- | --- |
| Người mới, chưa có `.env` và chưa có Docker volume | Làm theo [mục 2](#2-chạy-lần-đầu-cho-người-mới) |
| Đã chạy dự án trước đây, còn `.env` và dữ liệu Docker | Chạy `docker compose up -d --build`, rồi mở `https://localhost` |
| Chỉ sửa code frontend | Chỉ refresh trình duyệt |
| Sửa code backend hoặc thêm dependency | Chạy `docker compose up -d --build` |
| Muốn giữ dữ liệu cũ | Không dùng `docker compose down -v` |

---

# 2. CHẠY LẦN ĐẦU CHO NGƯỜI MỚI

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

Để bật **Đăng nhập bằng Google**, thêm hoặc kiểm tra dòng sau trong `.env`:

```ini
GOOGLE_CLIENT_ID=869671892121-o2un8vci63vtdpio7rgv5spdv525vo1u.apps.googleusercontent.com
```

Frontend đã dùng cùng Client ID này. Khi triển khai trên domain khác
(`localhost` không cần thêm cấu hình), hãy thêm domain đó vào **Authorized JavaScript origins**
trong Google Cloud Console.

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

API kiểm tra nhanh:

```bash
curl http://localhost:8000/health
```

Lần đầu trình duyệt báo **"Kết nối của bạn không phải là kết nối riêng tư"**. Đây là bình thường: hệ thống dùng chứng chỉ tự ký. Bấm **Nâng cao → Tiếp tục truy cập localhost**. Mỗi thiết bị chỉ phải làm một lần.

> **Vì sao phải HTTPS?** Trình duyệt chỉ cho phép dùng micro và camera trên kết nối bảo mật. Không có HTTPS thì tính năng gọi điện không chạy.

---

# 3. CẤU HÌNH ĐĂNG NHẬP BẰNG GOOGLE

Phần này dành cho trường hợp bạn muốn tự tạo Client ID riêng trên Google Cloud Console
thay vì dùng Client ID mẫu đã có trong dự án.

## 3.1. Tạo hoặc chọn Google Cloud Project

1. Mở [Google Cloud Console](https://console.cloud.google.com/).
2. Đăng nhập bằng tài khoản Google của bạn.
3. Ở thanh phía trên, bấm **Select a project** → **New Project**.
4. Đặt tên, ví dụ `team-chat`, rồi bấm **Create**.
5. Chọn project vừa tạo.

## 3.2. Cấu hình OAuth consent screen

1. Vào **APIs & Services** → **OAuth consent screen**.
2. Chọn **External** nếu người dùng đăng nhập bằng các tài khoản Gmail khác
   ngoài tổ chức Google Workspace của bạn.
3. Điền tối thiểu:
   - **App name**: `Team Chat`
   - **User support email**: email của bạn
   - **Developer contact information**: email của bạn
4. Bấm **Save and Continue** qua các bước còn lại.
5. Nếu ứng dụng đang ở trạng thái **Testing**, vào phần **Test users** → **Add users**
   và thêm các địa chỉ Gmail được phép đăng nhập thử.

> Khi ứng dụng ở trạng thái Testing, chỉ những tài khoản trong danh sách Test users
> mới đăng nhập được. Nếu thấy lỗi `access_denied` hoặc ứng dụng chưa được Google xác minh,
> hãy kiểm tra lại danh sách này.

## 3.3. Tạo OAuth Client ID cho website

1. Vào **APIs & Services** → **Credentials**.
2. Bấm **+ CREATE CREDENTIALS** → **OAuth client ID**.
3. Ở **Application type**, chọn **Web application**.
4. Đặt tên, ví dụ `Team Chat Web`.
5. Trong **Authorized JavaScript origins**, thêm đúng các origin bạn dùng:

```text
https://localhost
http://localhost:8080
```

Nếu chạy frontend bằng server khác, thêm origin tương ứng, ví dụ:

```text
http://localhost:3000
https://chat.example.com
```

Chỉ nhập origin gồm giao thức, hostname và port; **không thêm dấu `/` ở cuối**,
không nhập đường dẫn như `/login`.

6. Với cơ chế GIS hiện tại, không cần thêm **Authorized redirect URI**.
7. Bấm **Create**.
8. Sao chép giá trị **Client ID** có dạng:

```text
123456789012-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.apps.googleusercontent.com
```

> Chỉ dùng **Client ID**, không dùng Client Secret ở frontend. Client Secret không được
> đưa vào Git, HTML hoặc JavaScript trình duyệt.

## 3.4. Gắn Client ID vào dự án

Mở file `.env` ở thư mục gốc và thay Client ID:

```ini
GOOGLE_CLIENT_ID=Client_ID_cua_ban.apps.googleusercontent.com
```

Frontend hiện đang dùng Client ID trong file [app.js](./frontend/js/app.js).
Nếu bạn thay sang Client ID riêng, hãy thay cùng một giá trị ở phần cấu hình
`client_id` trong file đó.

Sau đó build lại backend và frontend:

```bash
docker compose up -d --build
```

Mở lại `https://localhost` bằng **Ctrl + F5**, bấm nút **Đăng nhập bằng Google**
và chọn tài khoản Gmail đã thêm trong **Test users**.

## 3.5. Khi chạy bằng HTTPS localhost hoặc domain thật

Google kiểm tra origin rất chính xác. Các địa chỉ sau là khác nhau:

```text
https://localhost
http://localhost:8080
http://localhost:3000
https://chat.example.com
```

Bạn phải thêm từng origin thực tế vào **Authorized JavaScript origins**.
Không thêm `*`, không thêm URL API `/api`, và không thêm đường dẫn `/login`.

Nếu trình duyệt báo:

```text
The given origin is not allowed for the given client ID
```

hãy kiểm tra ba điểm:

1. Địa chỉ trên thanh trình duyệt có đúng với origin đã khai báo không.
2. Client ID trong `.env` và `frontend/js/app.js` có giống nhau không.
3. Bạn đã bấm **Save** trong Google Cloud Console và chờ vài phút để cấu hình cập nhật chưa.

---

# 4. TÀI KHOẢN DÙNG THỬ

Mật khẩu chung: **`password123`**

| Email | Tên | Vai trò trong `# Phòng Kiến Trúc` |
| --- | --- | --- |
| `user1@example.com` | Nguyễn Xuân Dũng | **Chủ phòng** — đủ mọi quyền |
| `user2@example.com` | Trần Văn Nam | **Quản trị viên** — xóa tin người khác, thêm/xóa thành viên |
| `user3@example.com` | Lê Hoàng Anh | Thành viên thường |
| `user4@example.com` | Phạm Phương Mai | **Chưa vào phòng nào** — để thử mời thành viên |

Ngoài ra có phòng riêng tư `🔒 Nhóm Trưởng`, chỉ `user1` và `user2` nhìn thấy.

---

# 5. CÁC LẦN SAU

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

# 6. THỬ TỪNG TÍNH NĂNG

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

# 7. THỬ TRÊN ĐIỆN THOẠI VÀ MÁY KHÁC

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

## Muốn gọi khi khác mạng

Xem [mục 5B](#5b-gọi-qua-internet-khác-mạng).

---

# 6B. GỌI QUA INTERNET (khác mạng)

Mặc định chỉ gọi được trong **cùng một mạng**. Muốn gọi khi hai người ở hai mạng
khác nhau cần thêm hai thứ, cả hai đều nằm ngoài code.

## Vì sao cần hai thứ

**Tunnel** — để người ngoài vào được server đang chạy trên máy bạn.

**TURN** — máy chủ trung gian chuyển tiếp âm thanh/hình ảnh. Hệ thống đã cấu hình
sẵn STUN của Google, đủ cho phần lớn mạng gia đình. Nhưng 4G và mạng công ty,
trường học thường chặn kết nối trực tiếp; khi đó thiếu TURN thì cuộc gọi báo
*"Không kết nối được tới người bên kia"*.

## Bước 1: Khai báo TURN

Sửa `ICE_SERVERS` trong `.env`. Hai cách viết, dùng cách nào cũng được:

```ini
# Cách ngắn: các mục cách nhau bằng dấu phẩy, TURN thêm |username|password
ICE_SERVERS=stun:stun.l.google.com:19302,turn:vidu.com:3478|user|pass

# Cách JSON, khi một máy chủ có nhiều url
ICE_SERVERS=[{"urls":["turn:vidu.com:3478","turn:vidu.com:3478?transport=tcp"],"username":"user","credential":"pass"}]
```

Lấy tài khoản TURN ở đâu: đăng ký một dịch vụ có gói miễn phí (Metered,
Cloudflare Realtime...), hoặc tự dựng bằng coturn nếu có máy chủ IP công khai.

Áp dụng thay đổi — phải dùng `up -d`, vì `restart` **không** đọc lại `.env`:

```bash
docker compose up -d backend
```

Kiểm tra cấu hình trước khi gọi thử:

```bash
docker compose exec backend python check_turn.py
```

## Bước 2: Mở tunnel

```powershell
winget install --id Cloudflare.cloudflared
```

```bash
cloudflared tunnel --url http://localhost:8080
```

Cloudflared in ra địa chỉ dạng `https://abc-xyz.trycloudflare.com` — gửi cho ai
cũng vào được, kèm **chứng chỉ thật** nên không còn cảnh báo bảo mật.

Giữ cửa sổ này mở. Cổng 8080 là cổng HTTP nội bộ dành riêng cho tunnel, chỉ mở
trên localhost nên người trong LAN không vào bằng HTTP không mã hóa được.

## Chế độ thử TURN trên một máy

Bình thường hai cửa sổ trên cùng máy sẽ nối thẳng, không dùng TURN. Muốn thấy
TURN hoạt động mà không cần hai mạng, mở trang kèm tham số:

```
https://localhost/?relay=1
```

Mọi cuộc gọi khi đó bị cấm đi thẳng, buộc phải vòng qua TURN. Màn hình cuộc gọi
hiện dải vàng cảnh báo, và dòng trạng thái chuyển thành *"Đang chuyển tiếp qua
máy chủ trung gian"*. Tiện để quay video demo hoặc chụp ảnh cho báo cáo.

Tải lại trang không kèm `?relay=1` là trở về bình thường — chế độ này không lưu
lại ở đâu cả.

> ⚠️ Chỉ dùng khi cần: ép qua TURN làm mọi cuộc gọi tiêu tốn hạn mức băng thông
> và tăng độ trễ, kể cả khi hai máy ngồi cạnh nhau.

## Kiểm tra cuộc gọi đang đi đường nào

Trong màn hình cuộc gọi có một dòng chữ nhỏ dưới tên người gọi:

| Hiện | Nghĩa là |
| --- | --- |
| Kết nối trực tiếp giữa các máy | Đi thẳng, không tốn băng thông TURN |
| Đang chuyển tiếp qua máy chủ trung gian (TURN) | Không nối thẳng được, đang qua TURN |

## Thử TURN tại chỗ, không cần đăng ký

Dự án có sẵn một máy chủ TURN để thử. Điền **IP LAN thật** của máy vào `.env`:

```ini
TURN_EXTERNAL_IP=192.168.1.18
ICE_SERVERS=turn:192.168.1.18:3478|test|test123
```

```bash
docker compose --profile turn up -d
```

> ⚠️ **Không dùng `127.0.0.1` cho TURN.** Chromium lặng lẽ bỏ qua máy chủ TURN đặt
> ở địa chỉ loopback — không báo lỗi, không gửi gói tin nào, rất khó đoán ra.

## Giới hạn

- Địa chỉ tunnel đổi mỗi lần chạy lại (bản miễn phí)
- Tắt máy là tắt hệ thống
- Thông tin đăng nhập TURN lộ ra trình duyệt, đây là bản chất của WebRTC — đừng
  dùng tài khoản trả tiền cho bản demo công khai

---

# 8. LỆNH BẢO TRÌ

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

Nếu database được tạo từ phiên bản cũ, cập nhật thủ công một lần bằng lệnh sau
(backend mới cũng tự thực hiện lệnh tương tự khi khởi động):

```bash
docker compose exec -T db psql -U postgres -d teamchat_db \
  -c 'ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;'
docker compose restart backend
```

## Reset toàn bộ dữ liệu

```bash
docker compose down -v
docker compose up -d
docker compose exec backend python seed_users.py
```

---

# 9. XỬ LÝ SỰ CỐ

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

# 10. CHECKLIST TRƯỚC KHI DEMO

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

# 11. PHỤ LỤC: CHẠY KHÔNG CẦN NGINX

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

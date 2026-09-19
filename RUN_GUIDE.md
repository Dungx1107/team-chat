# HƯỚNG DẪN VẬN HÀNH HỆ THỐNG TEAM CHAT

Tài liệu này hướng dẫn toàn bộ quy trình vận hành hệ thống **Team Chat**, từ khởi động Docker, khởi tạo dữ liệu mẫu, chạy Frontend đến kiểm thử chức năng chat trên một hoặc nhiều thiết bị trong cùng mạng LAN/Wi-Fi.

## Kiến trúc triển khai

Hệ thống gồm các thành phần chính:

| Thành phần | Cách triển khai    | Mục đích                               |
| ---------- | ------------------ | -------------------------------------- |
| Backend    | Docker Container   | Xử lý API, xác thực và logic nghiệp vụ |
| PostgreSQL | Docker Container   | Lưu trữ dữ liệu hệ thống               |
| Frontend   | Python HTTP Server | Phục vụ giao diện Web                  |
| Client     | Trình duyệt Web    | Đăng nhập và sử dụng hệ thống          |

Để kiểm thử nhiều thiết bị, Frontend được bind vào `0.0.0.0`, cho phép các thiết bị khác trong cùng mạng LAN/Wi-Fi truy cập thông qua địa chỉ IP nội bộ của máy chủ.

---

## MỤC LỤC

1. [Tài khoản dùng thử](#1-tài-khoản-dùng-thử)
2. [Chạy hệ thống trên Ubuntu/Linux](#2-chạy-hệ-thống-trên-ubuntulinux)
3. [Chạy hệ thống trên Windows](#3-chạy-hệ-thống-trên-windows)
4. [Kiểm thử chat trên nhiều thiết bị](#4-kiểm-thử-chat-trên-nhiều-thiết-bị)
5. [Lệnh bảo trì và xử lý lỗi](#5-lệnh-bảo-trì-và-xử-lý-lỗi)
6. [Quy trình chạy nhanh](#6-quy-trình-chạy-nhanh)
7. [Checklist trước khi demo](#7-checklist-trước-khi-demo)

---

# 1. TÀI KHOẢN DÙNG THỬ

Hệ thống được cấu hình sẵn 3 tài khoản phục vụ việc kiểm thử.

**Mật khẩu chung:** `password123`

| Họ và tên        | Username | Email đăng nhập     | Mật khẩu      | Quyền                         |
| ---------------- | -------- | ------------------- | ------------- | ----------------------------- |
| Nguyễn Xuân Dũng | `dungx`  | `user1@example.com` | `password123` | Chủ phòng `# Phòng Kiến Trúc` |
| Trần Văn Nam     | `namtv`  | `user2@example.com` | `password123` | Thành viên                    |
| Lê Hoàng Anh     | `anhlh`  | `user3@example.com` | `password123` | Thành viên                    |

> **Lưu ý:** Đây là tài khoản phục vụ mục đích demo/kiểm thử.

---

# 2. CHẠY HỆ THỐNG TRÊN UBUNTU/LINUX

## Bước 1: Khởi động Docker

Mở **Terminal 1** và di chuyển vào thư mục project:

```bash
cd ~/Workspace/VNU-UET/nam4/hk1/kien-truc-phan-mem/team-chat
```

Khởi động toàn bộ Docker services:

```bash
docker compose up -d
```

Kiểm tra trạng thái:

```bash
docker compose ps
```

Backend và PostgreSQL cần ở trạng thái đang chạy.

Nếu project có cấu hình `healthcheck`, hãy chờ đến khi các service chuyển sang trạng thái `healthy`.

---

## Bước 2: Nạp dữ liệu tài khoản mẫu

Vẫn trong **Terminal 1**, chạy:

```bash
docker compose exec backend python seed_users.py
```

Lệnh này tạo các tài khoản dùng thử trong database.

Kiểm tra dữ liệu:

```bash
docker compose exec db psql -U postgres -d teamchat_db -c "SELECT id, email, username FROM users;"
```

Kết quả cần có 3 tài khoản:

```text
user1@example.com
user2@example.com
user3@example.com
```

---

## Bước 3: Khởi động Frontend

Mở **Terminal 2**.

Di chuyển vào thư mục Frontend:

```bash
cd ~/Workspace/VNU-UET/nam4/hk1/kien-truc-phan-mem/team-chat/frontend
```

Khởi động HTTP Server:

```bash
python3 -m http.server 3000 --bind 0.0.0.0
```

Nếu xuất hiện:

```text
Serving HTTP on 0.0.0.0 port 3000
```

thì Frontend đã sẵn sàng.

> **Lưu ý:** Giữ Terminal 2 mở trong suốt quá trình kiểm thử. Đóng Terminal sẽ dừng HTTP Server.

---

# 3. CHẠY HỆ THỐNG TRÊN WINDOWS

## Bước 1: Khởi động Docker Desktop

Mở **Docker Desktop** từ Start Menu.

Chờ Docker Engine khởi động hoàn toàn.

Sau đó mở **PowerShell** hoặc **Windows Terminal**.

Kiểm tra Docker:

```powershell
docker --version
```

Kiểm tra Docker Compose:

```powershell
docker compose version
```

Nếu Docker Desktop gặp lỗi liên quan đến WSL 2, mở PowerShell với quyền Administrator và chạy:

```powershell
wsl --update
```

Sau đó khởi động lại máy nếu Windows yêu cầu.

---

## Bước 2: Khởi động Docker Services

Mở **PowerShell 1**.

Di chuyển vào thư mục project:

```powershell
cd <ĐƯỜNG_DẪN>\team-chat
```

Ví dụ:

```powershell
cd D:\Workspace\team-chat
```

Khởi động Docker:

```powershell
docker compose up -d
```

Kiểm tra trạng thái:

```powershell
docker compose ps
```

---

## Bước 3: Nạp dữ liệu tài khoản mẫu

Vẫn trong **PowerShell 1**, chạy:

```powershell
docker compose exec backend python seed_users.py
```

Kiểm tra database:

```powershell
docker compose exec db psql -U postgres -d teamchat_db -c "SELECT id, email, username FROM users;"
```

Kết quả cần có:

```text
user1@example.com
user2@example.com
user3@example.com
```

---

## Bước 4: Khởi động Frontend

Mở **PowerShell 2**.

Di chuyển vào thư mục Frontend:

```powershell
cd <ĐƯỜNG_DẪN>\team-chat\frontend
```

Ví dụ:

```powershell
cd D:\Workspace\team-chat\frontend
```

Khởi động HTTP Server:

```powershell
python -m http.server 3000 --bind 0.0.0.0
```

Nếu xuất hiện:

```text
Serving HTTP on 0.0.0.0 port 3000
```

thì Frontend đã sẵn sàng.

Nếu Windows Firewall hiển thị cảnh báo, cho phép Python truy cập mạng **Private Network** nếu muốn các thiết bị khác trong cùng mạng LAN truy cập Frontend.

> **Lưu ý:** Giữ PowerShell 2 mở trong suốt quá trình kiểm thử.

---

# 4. KIỂM THỬ CHAT TRÊN NHIỀU THIẾT BỊ

## 4.1. Kiểm thử trên cùng một máy

Có thể sử dụng:

* Hai cửa sổ trình duyệt khác nhau.
* Hoặc một cửa sổ bình thường và một cửa sổ ẩn danh.

### Trình duyệt 1

Truy cập:

```text
http://localhost:3000
```

Đăng nhập bằng:

```text
Email:    user1@example.com
Password: password123
```

### Trình duyệt 2

Mở cửa sổ ẩn danh:

```text
Ctrl + Shift + N
```

Truy cập:

```text
http://localhost:3000
```

Đăng nhập bằng:

```text
Email:    user2@example.com
Password: password123
```

### Kiểm tra chức năng chat

Trên cả hai cửa sổ:

1. Mở phòng `# Phòng Kiến Trúc`.
2. Từ tài khoản `user1@example.com`, gửi một tin nhắn.
3. Kiểm tra tài khoản `user2@example.com` có nhận được tin nhắn.
4. Từ tài khoản `user2@example.com`, gửi phản hồi.
5. Kiểm tra tài khoản `user1@example.com` có nhận được tin nhắn.

Nếu tin nhắn được gửi và nhận giữa hai tài khoản, chức năng chat cơ bản hoạt động.

---

## 4.2. Kiểm thử giữa hai máy tính

Hai máy tính phải kết nối vào **cùng một mạng LAN/Wi-Fi**.

### Bước 1: Xác định địa chỉ IP của máy chủ

Máy chủ là máy đang chạy:

```text
Python HTTP Server
```

### Ubuntu/Linux

Chạy:

```bash
hostname -I
```

Ví dụ:

```text
192.168.1.25
```

Có thể lấy địa chỉ IP đầu tiên bằng:

```bash
hostname -I | awk '{print $1}'
```

### Windows

Chạy:

```powershell
ipconfig
```

Tìm dòng:

```text
IPv4 Address
```

Ví dụ:

```text
IPv4 Address. . . . . . . . . . . : 192.168.1.25
```

---

### Bước 2: Truy cập từ máy thứ hai

Trên máy tính thứ hai, mở trình duyệt và truy cập:

```text
http://<IP_MÁY_CHẠY_SERVER>:3000
```

Ví dụ:

```text
http://192.168.1.25:3000
```

Đăng nhập bằng tài khoản khác:

```text
Email:    user3@example.com
Password: password123
```

Sau đó mở phòng:

```text
# Phòng Kiến Trúc
```

và gửi tin nhắn.

Máy chủ có thể đăng nhập bằng:

```text
user1@example.com
```

hoặc:

```text
user2@example.com
```

để kiểm tra quá trình trao đổi tin nhắn giữa hai máy.

---

## 4.3. Kiểm thử bằng điện thoại

Điện thoại phải kết nối vào **cùng mạng Wi-Fi** với máy đang chạy Frontend Server.

Trên điện thoại, mở trình duyệt và truy cập:

```text
http://<IP_MÁY_CHẠY_SERVER>:3000
```

Ví dụ:

```text
http://192.168.1.25:3000
```

Đăng nhập:

```text
Email:    user3@example.com
Password: password123
```

Mở phòng:

```text
# Phòng Kiến Trúc
```

Gửi tin nhắn từ điện thoại.

Trên máy tính, kiểm tra xem tin nhắn có xuất hiện hay không.

Sau đó gửi một tin nhắn từ máy tính và kiểm tra trên điện thoại.

Nếu hai thiết bị có thể gửi và nhận tin nhắn, kết nối giữa các client đang hoạt động.

---

# 5. LỆNH BẢO TRÌ VÀ XỬ LÝ LỖI

## 5.1. Xem log Backend

Theo dõi log Backend theo thời gian thực:

```bash
docker compose logs -f backend
```

Nhấn:

```text
Ctrl + C
```

để thoát.

---

## 5.2. Xem log toàn bộ hệ thống

```bash
docker compose logs -f
```

Lệnh này hữu ích khi cần kiểm tra đồng thời Backend và Database.

---

## 5.3. Khởi động lại Backend

Nếu Backend gặp lỗi:

```bash
docker compose restart backend
```

Sau đó kiểm tra:

```bash
docker compose ps
```

---

## 5.4. Dừng hệ thống

Dừng toàn bộ Docker services:

```bash
docker compose down
```

Lệnh này dừng và xóa các containers nhưng **không xóa Docker volumes**.

---

## 5.5. Khởi động lại hệ thống

Khởi động lại Docker services:

```bash
docker compose up -d
```

Kiểm tra:

```bash
docker compose ps
```

---

## 5.6. Reset hoàn toàn Database

> **CẢNH BÁO:** Lệnh `docker compose down -v` sẽ xóa các Docker volumes liên quan. Dữ liệu hiện có trong database có thể bị mất.

Thực hiện:

```bash
docker compose down -v
docker compose up -d
docker compose exec backend python seed_users.py
```

Kiểm tra lại database:

```bash
docker compose exec db psql -U postgres -d teamchat_db -c "SELECT id, email, username FROM users;"
```

---

# 6. QUY TRÌNH CHẠY NHANH

Nếu hệ thống đã được cài đặt đầy đủ, quy trình chạy hằng ngày chỉ gồm hai Terminal.

## Terminal 1: Backend + Database

Di chuyển vào thư mục project:

```bash
cd <ĐƯỜNG_DẪN>\team-chat
```

Khởi động Docker:

```bash
docker compose up -d
```

Nếu cần nạp lại dữ liệu mẫu:

```bash
docker compose exec backend python seed_users.py
```

## Terminal 2: Frontend

Di chuyển vào thư mục Frontend:

```bash
cd <ĐƯỜNG_DẪN>\team-chat\frontend
```

### Ubuntu/Linux

```bash
python3 -m http.server 3000 --bind 0.0.0.0
```

### Windows

```powershell
python -m http.server 3000 --bind 0.0.0.0
```

## Truy cập hệ thống

### Trên chính máy chạy server

```text
http://localhost:3000
```

### Trên máy tính hoặc điện thoại khác

```text
http://<IP_MÁY_CHẠY_SERVER>:3000
```

Ví dụ:

```text
http://192.168.1.25:3000
```

---

# 7. CHECKLIST TRƯỚC KHI DEMO

## Docker

* [ ] Docker Engine/Docker Desktop đang chạy.
* [ ] `docker compose up -d` thực hiện thành công.
* [ ] Backend đang hoạt động.
* [ ] PostgreSQL đang hoạt động.

## Database

* [ ] Đã chạy `seed_users.py`.
* [ ] Database có đủ 3 tài khoản thử nghiệm.
* [ ] Có thể đăng nhập bằng các tài khoản mẫu.

## Frontend

* [ ] Frontend Server đang chạy.
* [ ] Port `3000` đang được sử dụng.
* [ ] Có thể truy cập `http://localhost:3000`.
* [ ] Server được bind vào `0.0.0.0` khi cần test nhiều thiết bị.

## Kiểm thử nhiều thiết bị

* [ ] Máy chủ và client cùng mạng LAN/Wi-Fi.
* [ ] Đã xác định đúng IP nội bộ của máy chủ.
* [ ] Client có thể truy cập `http://<IP_MÁY_CHẠY_SERVER>:3000`.
* [ ] Hai tài khoản có thể đăng nhập.
* [ ] Hai tài khoản có thể truy cập `# Phòng Kiến Trúc`.
* [ ] Tin nhắn có thể gửi từ client này sang client khác.
* [ ] Tin nhắn có thể nhận theo chiều ngược lại.

---

# KẾT LUẬN

Để hệ thống Team Chat hoạt động đầy đủ, cần duy trì **hai nhóm thành phần**:

1. **Docker Compose**

   * Backend
   * PostgreSQL Database

2. **Python HTTP Server**

   * Phục vụ Frontend trên port `3000`.

Khi kiểm thử trên nhiều thiết bị, Frontend phải được chạy với:

```text
--bind 0.0.0.0
```

Thiết bị khác trong cùng mạng LAN/Wi-Fi không truy cập bằng `localhost`, mà phải sử dụng địa chỉ IP nội bộ của máy chạy server:

```text
http://<IP_MÁY_CHẠY_SERVER>:3000
```

Ví dụ:

```text
http://192.168.1.25:3000
```

Đây là quy trình chuẩn để khởi động, kiểm thử và xử lý các lỗi cơ bản của hệ thống Team Chat.

```
```

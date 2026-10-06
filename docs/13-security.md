# 13. Bảo mật

Hai phần tách bạch: **cơ chế đã có** (mô tả được như tính năng) và **rủi ro còn lại** (không
được mô tả như tính năng).

## Phần A — Cơ chế đã có

### Danh tính

| Cơ chế | Ở đâu | Chặn được |
|---|---|---|
| Băm mật khẩu bcrypt, 12 vòng, có muối | `infra/security/password.py` | Lộ DB không lộ mật khẩu |
| Thông báo đăng nhập sai chung một câu | `AuthService.login` | Dò email nào đã có tài khoản qua form đăng nhập |
| Access token sống ngắn (60 phút) | `infra/security/jwt.py` | Token bị lộ chỉ dùng được thời gian ngắn |
| Refresh token chỉ lưu hash SHA-256 | `refresh_tokens.token_hash` | Lộ DB không dùng lại được token |
| Luân chuyển refresh token, dùng một lần | `AuthService.rotate_refresh_token` | |
| **Phát hiện dùng lại** → thu hồi mọi token của người đó | như trên | Token bị đánh cắp và dùng song song với chủ thật |
| Xác minh Google ID Token bằng chữ ký + đúng Client ID + email đã xác minh | `AuthService.login_with_google` | Token giả; token cấp cho ứng dụng khác |
| Kiểm tra token tập trung ở middleware | `api/middlewares/auth_middleware.py` | Quên kiểm tra ở một endpoint |
| Đường dẫn công khai cho ảnh đại diện **chỉ với GET** | như trên | Lách xác thực bằng `POST` lên đường dẫn công khai |

### Phân quyền

| Cơ chế | Chặn được |
|---|---|
| Mọi thao tác với tin nhắn đòi là thành viên phòng (`MessageService._require_membership`) | Đọc tin phòng người khác — **lỗ hổng có trong bản baseline ban đầu**: ai đăng nhập cũng đọc được mọi phòng, kể cả riêng tư |
| Vai trò OWNER > ADMIN > MEMBER kiểm tra trong thực thể `RoomMember` | Leo quyền |
| ADMIN không xóa được ADMIN khác (`outranks`) | ADMIN xóa lẫn nhau |
| Lệnh chặn người bị xóa, kiểm tra ở **cửa vào duy nhất** `join_room` | Bị xóa rồi tự vào lại |
| Gửi tin không tự cho vào phòng | Lách lệnh chặn bằng cách gửi tin |
| Đăng nhập Google không tự cho vào phòng | Lách lệnh chặn bằng cách đăng nhập lại |
| `subscribe` WebSocket đòi là thành viên | Nghe lén tin của phòng công khai mà không tham gia; người bị xóa nghe tiếp |
| Thu hồi kênh realtime khi bị xóa (`revoke_room_access`) | Người bị xóa tiếp tục nhận tin qua kết nối đang mở |
| Tín hiệu WebRTC chỉ chuyển giữa hai người cùng cuộc gọi đang mở, tối đa 64 KB | Dùng WebSocket làm kênh nhắn riêng tới bất kỳ ai |
| Tải tệp đính kèm đòi là thành viên phòng chứa tệp | Đoán `attachment_id` để tải tệp phòng khác |

### Dữ liệu đầu vào

| Cơ chế | Chặn được |
|---|---|
| Pydantic kiểm tra mọi body: độ dài, kiểu, mẫu (`#rrggbb`, `AUDIO\|VIDEO`, ...) | Dữ liệu sai định dạng vào tới service |
| Thực thể kiểm tra quy tắc (tin rỗng, emoji lạ, tệp > 25 MB) | Dữ liệu sai nghiệp vụ vào DB |
| `escapeHtml()` cho mọi dữ liệu người dùng trước khi ghép HTML (`frontend/js/ui.js`) | **XSS** — bản baseline chèn tin nhắn thẳng bằng `innerHTML` |
| Tên tệp lưu bằng UUID, `_safe_path()` kiểm tra đường dẫn | Path traversal (`../../etc/passwd`), ghi đè tệp |
| Escape `%` và `_` khi tìm phòng | Liệt kê toàn bộ phòng công khai bằng ký tự đại diện |
| SQLAlchemy dùng tham số ràng buộc | SQL injection |

### Vận hành

| Cơ chế | Ghi chú |
|---|---|
| HTTPS, HTTP tự chuyển sang HTTPS | Chứng chỉ tự ký |
| Cổng tunnel 8080 chỉ mở trên `127.0.0.1` | Người trong LAN không vào được bằng HTTP không mã hóa |
| Container backend chạy bằng `appuser`, không phải root | |
| `.env` trong `.gitignore`; tệp `*_res.json`, `*.token`, `uploads/` cũng bị bỏ qua | Một tệp chứa token thật từng bị commit lên repo công khai và đã được gỡ |
| WebSocket tự đóng sau 90 giây im lặng | Kết nối chết giữ người dùng "online" và "đang bận" mãi |
| Mã hóa media WebRTC (DTLS-SRTP) bắt buộc theo chuẩn | Máy chủ TURN cũng không xem được nội dung cuộc gọi |

## Phần B — Rủi ro còn lại

Đây là những điều **chưa** làm. Không mô tả chúng như tính năng hiện có.

| # | Rủi ro | Mức | Ghi chú |
|---|---|---|---|
| 1 | Token nằm trong `localStorage` | Cao nếu có XSS | Đọc được bằng JavaScript. `escapeHtml` là lớp bảo vệ duy nhất — một chỗ quên escape là lộ token |
| 2 | Token WebSocket trong query string | Trung bình | Có thể nằm trong log của proxy, lịch sử trình duyệt |
| 3 | `JWT_SECRET_KEY` có giá trị mặc định trong code | Cao nếu quên đổi | Ai biết giá trị mặc định đều tự ký được token |
| 4 | Không giới hạn tần suất (rate limit) | Trung bình | Dò mật khẩu, spam tin nhắn, spam tạo phòng đều không bị chặn |
| 5 | `CORS_ORIGINS` mặc định `*` | Thấp | Token gửi qua header chứ không qua cookie nên CSRF khó xảy ra, nhưng nên thu hẹp khi công khai |
| 6 | Tìm người dùng khớp cả email | Thấp | Kết quả không chứa email, nhưng tìm theo email cho biết email đó có tài khoản |
| 7 | Ảnh đại diện công khai | Thấp | Ai biết `user_id` cũng xem được ảnh |
| 8 | Chứng chỉ tự ký | — | Chấp nhận được trong LAN, không dùng cho triển khai thật |
| 9 | Tệp tải lên không quét virus, không kiểm tra nội dung thật so với MIME khai báo | Trung bình | `content_type` do client khai |
| 10 | Tệp ghi xong mới kiểm tra kích thước | Thấp | nginx đã chặn ở 30 MB |
| 11 | Tệp của tin/phòng đã xóa vẫn nằm trên đĩa | Thấp | Người dùng tưởng đã xóa nhưng dữ liệu vẫn còn |
| 12 | `ACCESS_TOKEN_EXPIRE_MINUTES`, `MAX_UPLOAD_BYTES` trong cấu hình không có tác dụng | Thấp | Đổi cấu hình tưởng có hiệu lực nhưng không |
| 13 | Biệt danh không giới hạn theo vai trò | Thấp | Thành viên đặt biệt danh xúc phạm cho người khác được; bù lại có tin hệ thống ghi lại ai đặt |
| 14 | Không có nhật ký kiểm toán | — | Ai xóa ai, ai đổi vai trò chỉ thấy qua sự kiện realtime, không lưu lại (trừ `room_bans.banned_by`) |
| 15 | `refresh` không kiểm tra tài khoản còn hoạt động | Thấp | Tài khoản bị vô hiệu hóa vẫn đổi được token đến khi refresh token hết hạn |

## Bài học từ các lỗ hổng đã sửa

Các lỗ hổng tìm thấy trong quá trình phát triển đều có chung một dạng: **một quy tắc được kiểm
tra ở cửa chính nhưng có cửa phụ không kiểm tra.**

| Quy tắc | Cửa chính | Cửa phụ từng bị bỏ quên |
|---|---|---|
| Chỉ thành viên đọc được tin | — | Endpoint đọc tin không kiểm tra gì cả |
| Người bị xóa không vào lại | `join_room` | Gửi tin; đăng nhập Google; `subscribe` WebSocket |
| Người bị xóa không nhận tin | Hủy tư cách thành viên | Kết nối WebSocket đã mở từ trước |

Khi thêm một quy tắc truy cập, hãy liệt kê **mọi** đường dẫn tới cùng một tài nguyên: REST,
WebSocket, luồng đăng nhập, tác vụ nền.

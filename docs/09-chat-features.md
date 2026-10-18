# 9. Tính năng chat

Mô tả hành vi từ góc người dùng, kèm quy tắc nằm ở đâu trong code. Bảng quyền đầy đủ theo
vai trò: [06](06-authentication-authorization.md#ma-trận-quyền).

## Phòng

### Hai loại phòng

| | Công khai | Riêng tư |
|---|---|---|
| Hiện trong danh sách phòng | Chỉ khi **đã tham gia** | Chỉ khi đã tham gia |
| Tìm thấy theo tên | ✅ (trừ người bị chặn) | ❌ không bao giờ |
| Vào bằng cách | Tìm rồi bấm tham gia | Được thêm hoặc chấp nhận lời mời |
| Biểu tượng | | 🔒 |

**Danh sách phòng ở sidebar chỉ gồm phòng đã tham gia.** Phòng công khai chưa tham gia không
tự hiện ra — người dùng phải gõ tên vào ô tìm kiếm. Quy tắc này nằm ở
`RoomRepository.list_joined_by_user()` (truy vấn `JOIN room_members`).

### Tìm và tham gia

Ô tìm kiếm ở sidebar làm ba việc cùng lúc:

1. Lọc ngay tại chỗ danh sách phòng đã tham gia theo tên.
2. Sau 300 ms ngừng gõ, gọi song song `GET /rooms/search` và `GET /users/search`.
3. Hiện hai mục: **Phòng công khai** (chưa tham gia, tối đa 5) và **Người dùng** (tối đa 5).

Bấm vào phòng → `POST /rooms/{id}/join` → nạp lại danh sách → mở phòng. Nếu người dùng gõ
tiếp trong lúc đang chờ kết quả, kết quả cũ bị bỏ.

Tìm kiếm phòng:
- Khớp **một phần**, không phân biệt hoa thường (`ILIKE '%từ khóa%'`).
- `%` và `_` được hiểu là ký tự thường. Không escape thì tìm `%` sẽ liệt kê **mọi** phòng công
  khai, phá vỡ quy tắc "phải biết tên mới thấy".
- Bỏ qua phòng mà người tìm đã bị chặn.

### Tạo, sửa, xóa

| Hành động | Ai | Ghi chú |
|---|---|---|
| Tạo | Bất kỳ ai đăng nhập | Tên 1–150 ký tự, bắt buộc. Người tạo thành OWNER |
| Đổi tên, mô tả, màu chủ đề | OWNER, ADMIN | Màu là một trong 6 màu chọn sẵn trên giao diện, server nhận mọi mã `#rrggbb` |
| Đổi ảnh phòng | OWNER, ADMIN | JPEG/PNG/GIF/WEBP, ≤ 5 MB. Ảnh cũ bị xóa khỏi ổ đĩa |
| Xóa phòng | OWNER | Xóa theo mọi thành viên, tin nhắn, lệnh chặn, lời mời. Cuộc gọi giữ lại làm lịch sử |

### Thư viện tệp của phòng

`GET /rooms/{id}/media` liệt kê các tệp đã gửi trong phòng. Giao diện hiện trong hộp thoại cài
đặt phòng, mục "Ảnh, video và tệp"; bấm vào là tải về.

## Thành viên

### Ba cách vào phòng

| Cách | Phòng | Ai khởi xướng | Có cần đồng ý? | Gỡ lệnh chặn? |
|---|---|---|---|---|
| Tự tham gia | Công khai | Chính người đó | — | ❌ — bị chặn thì không vào được |
| Được thêm trực tiếp | Cả hai | OWNER, ADMIN | Không | ✅ |
| Chấp nhận lời mời | Cả hai | OWNER, ADMIN gửi | Có | ✅ |

### Ra khỏi phòng

| Cách | Ai | Hệ quả |
|---|---|---|
| Tự rời | ADMIN, MEMBER (OWNER không rời được) | Mất quyền ngay. **Không bị chặn** — muốn quay lại thì tìm và tham gia |
| Bị xóa | OWNER xóa bất kỳ ai; ADMIN xóa MEMBER | Mất quyền ngay. **Bị chặn**. Kênh realtime của phòng bị thu hồi |

### Chặn người bị xóa

Đây là tính năng có nhiều chi tiết nhất, vì một lệnh chặn chỉ có ý nghĩa nếu **mọi** cửa vào
đều kiểm tra nó.

Khi bị xóa, `RoomService.remove_member()`:

1. Xóa dòng trong `room_members`.
2. Ghi một dòng vào `room_bans` (trừ khi người đó tự xóa chính mình).
3. Phát `room.member_left` tới phòng — người bị xóa cũng nhận được, nên giao diện của họ báo
   "Bạn đã bị xóa khỏi phòng này" và đóng phòng.
4. Thu hồi kênh realtime của phòng khỏi kết nối của họ.

Từ lúc đó, người bị chặn:

| Thử | Kết quả |
|---|---|
| Tìm phòng theo tên | Không thấy |
| `POST /rooms/{id}/join` | `403` "Bạn đã bị xóa khỏi phòng này. Chỉ chủ phòng hoặc quản trị viên mới mời lại được" |
| Xem thông tin phòng, danh sách thành viên | `403` |
| Đọc tin, gửi tin, gửi tệp | `403` |
| Gửi lại lệnh `subscribe` qua WebSocket | Bị từ chối |
| Đăng nhập lại bằng Google | Không được thêm lại vào phòng nào |

Hai dòng cuối và việc gửi tin là các **cửa sau** từng tồn tại và đã được đóng — chi tiết ở
[06](06-authentication-authorization.md#chặn-người-bị-xóa).

### Vai trò

- Chỉ OWNER đổi vai trò, và chỉ giữa `ADMIN` và `MEMBER`. Không phong ai làm OWNER được.
- Không ai đổi được vai trò của OWNER.

### Lời mời

1. OWNER/ADMIN mở phần thêm thành viên, tìm người, bấm mời → `POST /rooms/{id}/invites`.
2. Người được mời nhận sự kiện `room.invite` ngay lập tức (dù đang mở phòng nào): thông báo nổi
   và số trên biểu tượng chuông tăng.
3. Mở chuông → **Nhận** hoặc **Từ chối**.
4. Nhận → vào phòng, gỡ lệnh chặn nếu có, tạo tin hệ thống "... đã vào phòng".

Lời mời đang chờ được nạp lại mỗi lần mở ứng dụng, nên không mất khi tải lại trang.

Không mời được người đã là thành viên, hoặc người đang có lời mời chờ cho phòng đó.

🐞 Mời lại một người đã từng chấp nhận lời mời của cùng phòng: lần chấp nhận thứ hai trả lỗi
`500`, dù người đó vẫn vào được phòng. Nguyên nhân và cách sửa: [05](05-database.md#room_invites).

### Biệt danh

Mỗi thành viên có thể có một biệt danh **riêng trong từng phòng** (`room_members.nickname`).

- Thành viên nào cũng đặt được biệt danh cho chính mình **và cho người khác** — không giới hạn
  theo vai trò.
- Mỗi lần đặt hoặc xóa sinh một tin nhắn hệ thống, ví dụ "Nguyễn Xuân Dũng đã đặt biệt danh cho
  Trần Văn Nam là Nam dev". Ai đặt gì đều công khai trong phòng.
- Để trống để xóa biệt danh.

## Tin nhắn

### Ba loại

| Loại | Tạo bởi | Quy tắc (trong thực thể `Message`) |
|---|---|---|
| `TEXT` | Người dùng | Nội dung 1–4000 ký tự, không được chỉ có khoảng trắng |
| `FILE` | Người dùng | Phải có tệp; nội dung là chú thích tùy chọn |
| `SYSTEM` | Hệ thống | Ví dụ: "... đã vào phòng", "... đã đặt biệt danh ..." |

**Phải là thành viên mới gửi được.** Gửi vào phòng công khai chưa tham gia trả `403`. (Trước
đây hệ thống tự cho vào phòng khi gửi tin — đó là một cửa sau vượt qua lệnh chặn.)

### Đọc tin

`GET /rooms/{id}/messages` trả **50 tin mới nhất**, sắp xếp cũ → mới để hiển thị.

Tham số `offset` lùi về quá khứ: `offset=50` là 50 tin trước đó. Hiện **giao diện chưa có**
chức năng cuộn lên để xem tin cũ hơn — phòng có hơn 50 tin thì tin cũ không xem được trên
giao diện, nhưng backend đã sẵn sàng.

Lỗi cũ cần biết: truy vấn từng sắp xếp cũ nhất trước rồi mới cắt 50, nên khi phòng có hơn 50
tin, tin vừa gửi **biến mất khi tải lại trang** (dù vẫn nằm trong DB và vẫn hiện tức thời qua
WebSocket). Đã sửa ở `MessageRepository.get_by_room_id()`.

### Trả lời — mới có ở backend

Backend nhận `reply_to_id` khi gửi tin và lưu lại; tin gốc bị xóa cứng thì `reply_to_id`
thành `NULL` (khóa ngoại `SET NULL`). Nhưng **giao diện chưa có** nút trả lời hay hiển thị
trích dẫn — `messages.js` không dùng `reply_to_id` ở đâu cả.

Tương tự, cột `forwarded_from_id` (chuyển tiếp tin) có trong bảng nhưng chưa có tính năng nào dùng.

### Sửa

- **Chỉ người gửi**, kể cả OWNER cũng không sửa được tin người khác.
- Đặt `edited_at`; giao diện hiện "(đã chỉnh sửa)".

### Xóa

- Người gửi xóa tin của mình; OWNER và ADMIN xóa được tin của bất kỳ ai.
- Là **xóa mềm**: `is_deleted = true`, nội dung bị xóa trắng, dòng vẫn còn. Giao diện hiện "Tin
  nhắn đã được thu hồi".
- Tệp đính kèm của tin đã xóa **vẫn nằm trên ổ đĩa**.

### Ghim

- OWNER và ADMIN ghim/bỏ ghim.
- Thanh tin ghim ở đầu phòng, mới ghim nhất trước.
- Cả ghim và bỏ ghim đều phát cùng một sự kiện `message.pinned`, phân biệt bằng trường `pinned`.

### Biểu cảm

- 6 loại: 👍 ❤️ 😂 😮 😢 🎉 — kiểm tra trong thực thể `Reaction`, loại khác bị từ chối.
- Bấm lần nữa là **gỡ** (giống Slack, Discord). Mỗi người mỗi loại một lần — ràng buộc duy nhất
  `(message_id, user_id, emoji)`.
- Sự kiện `message.reaction` gửi kèm danh sách đã gom theo loại: mỗi biểu cảm có số lượng và
  ai đã thả, để mọi client vẽ lại mà không phải gọi API.

### Tệp đính kèm

Chi tiết lưu trữ: [11](11-file-storage.md). Từ góc người dùng:

| Loại tệp | Hiển thị |
|---|---|
| Ảnh | Xem trực tiếp; bấm để phóng to |
| Video, âm thanh | Trình phát có sẵn của trình duyệt |
| Khác | Thẻ tệp với tên và dung lượng; bấm để tải |

Tối đa 25 MB mỗi tệp.

## Trạng thái tức thời

### Đang gõ

- Client gửi `typing.start` khi gõ, `typing.stop` khi ngừng hoặc gửi.
- Server phát cho **người khác** trong phòng, kèm tên và avatar.
- Server tự quên ai đang gõ sau 5 giây không cập nhật — phòng trường hợp client mất kết nối
  giữa chừng mà không kịp gửi `typing.stop`.

### Online

- Một người "online" khi có ít nhất một kết nối WebSocket. `GET /users/online` trả danh sách này.
- Danh sách thành viên hiện chấm xanh cho người online; nút gọi 1-1 bị khóa với người offline.
- Chấm xanh chỉ cập nhật khi **nạp lại** danh sách thành viên — backend có phát
  `user.online`/`user.offline` nhưng frontend chưa lắng nghe.

### Số tin chưa đọc

Có hiển thị trên sidebar nhưng **hiện gần như không hoạt động**: server không tính, còn
frontend chỉ đếm được với phòng đang theo dõi — mà phòng đó lại được đặt về 0 khi mở. Nguyên
nhân gốc: client chỉ theo dõi một phòng tại một thời điểm. Xem
[08](08-websocket-realtime.md#client-chỉ-theo-dõi-một-phòng-tại-một-thời-điểm).

## Hồ sơ

| Trường | Giới hạn | Ghi chú |
|---|---|---|
| Họ, tên | 1–50 ký tự mỗi trường | Hiển thị "Họ Tên" |
| Trạng thái | ≤ 100 ký tự | Ví dụ "Đang họp" — hiện dưới tên |
| Giới thiệu | ≤ 500 ký tự | |
| Ảnh đại diện | JPEG/PNG/GIF/WEBP, ≤ 5 MB | Chưa có ảnh thì hiện chữ cái đầu trên nền màu suy ra từ `user_id` |
| Email, username | Không đổi được | |

Đổi hồ sơ phát `user.updated` tới mọi phòng người đó đang ở, để tên và ảnh mới hiện ngay ở
mọi nơi.

Tài khoản tạo bằng Google lấy họ tên và ảnh từ Google lúc tạo; về sau sửa được như thường.

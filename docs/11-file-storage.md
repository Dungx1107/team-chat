# 11. Lưu trữ tệp

## Ba loại tệp, một chỗ lưu

`backend/app/domain/interfaces/file_storage.py` định nghĩa abstraction; `backend/app/infra/storage/supabase_storage.py` triển khai lưu trên Supabase Storage. File được đặt bằng UUID và chỉ giữ extension gốc, tránh dùng trực tiếp filename do client cung cấp.

Cả ba đều nằm phẳng trong một thư mục: `/app/uploads` trong container `backend`, gắn với
Docker volume **`uploads`**. Volume tách khỏi mã nguồn và khỏi dữ liệu PostgreSQL, nên dựng
lại container không mất tệp.

```text
Browser
 -> api.js multipart upload
 -> users.py/rooms.py/messages.py
 -> UserService/RoomService/MessageService
 -> SupabaseFileStorage.save()
 -> metadata AttachmentModel hoặc avatar path
 -> Supabase Storage bucket
 -> response URL/id
```

Lý do:

| Mối nguy | Cách tên UUID chặn |
|---|---|
| Hai người tải lên cùng tên `bao-cao.pdf` | Không bao giờ trùng |
| Tên gốc lộ thông tin | Tên trên ổ đĩa không nói gì |
| **Path traversal**: tên tệp `../../etc/passwd` | Không dùng tên gốc làm đường dẫn |

Thêm một lớp nữa ở `_safe_path()`: mọi đường dẫn đều cắt chỉ còn phần tên (`basename`), rồi
kiểm tra đường dẫn tuyệt đối sau khi giải vẫn nằm trong thư mục gốc. Áp dụng cho cả đọc và
xóa, không chỉ ghi.

Backend dùng `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` và `SUPABASE_STORAGE_BUCKET` để truy cập bucket Supabase. Vì file nằm ngoài container nên không phụ thuộc vòng đời Docker; Compose chỉ bind mount mã nguồn `./backend:/app`.

Lưu ý: tệp được **ghi xong rồi mới** kiểm tra kích thước, vì kích thước thật chỉ biết sau khi
ghi. Tệp quá lớn bị xóa ngay sau đó. nginx chặn trước ở mức 30 MB (`client_max_body_size`),
nên không ai đẩy được tệp khổng lồ vào đĩa.

## Tải tệp về

Tệp đính kèm cần quyền: `GET /api/attachments/{id}` kiểm tra người tải là thành viên phòng
chứa tin đó. Vì cần header `Authorization`, frontend **không** đặt URL thẳng vào `<img src>`
mà:

1. `fetch` có kèm token → nhận về `Blob`
2. `URL.createObjectURL(blob)` → địa chỉ `blob:...` chỉ sống trong tab đó
3. Gán địa chỉ này vào `<img>`, `<video>`, `<audio>`

Việc này nằm ở `hydrateSecureMedia()` trong `messages.js`: mọi phần tử có thuộc tính
`data-secure-src` được thay bằng `blob:` URL sau khi hiển thị tin nhắn.

Ảnh đại diện thì ngược lại: là đường dẫn công khai, vì xuất hiện ở khắp nơi và tải bằng
`fetch` từng cái thì quá nặng. Đổi lại, ai biết `user_id` cũng xem được ảnh đại diện — chấp
nhận được với ảnh đại diện.

Đổi ảnh đại diện thì frontend thêm `?v=<thời điểm>` vào URL để trình duyệt không dùng lại ảnh
cũ trong cache.

## Xóa tệp

| Khi | Tệp trên ổ đĩa |
|---|---|
| Đổi ảnh đại diện (người hoặc phòng) | ✅ Ảnh cũ bị xóa |
| Tải lên quá giới hạn hoặc sai định dạng | ✅ Bị xóa ngay |
| Xóa tin nhắn (xóa mềm) | ❌ **Còn nguyên** |
| Xóa phòng | ❌ **Còn nguyên** — dòng `attachments` cũng còn |

Hai dòng cuối nghĩa là volume `uploads` chỉ lớn lên. Cần một tác vụ dọn tệp mồ côi nếu chạy
lâu dài.

## Sao lưu và xóa sạch

```bash
# Xem dung lượng
docker compose exec backend du -sh /app/uploads

# Xóa sạch MỌI tệp (không thể khôi phục)
docker compose down
docker volume rm team-chat_uploads
docker compose up -d
```

`SupabaseFileStorage.save()` đọc toàn bộ upload trước khi gửi lên Supabase; giới hạn Nginx request là `30m`, lớn hơn giới hạn attachment 25 MB. Bucket cần được tạo trước trong Supabase Dashboard. Hệ thống chưa có virus scanning hoặc content sniffing độc lập được xác định từ source.

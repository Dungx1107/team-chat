# 11. File storage

## Adapter

`backend/app/domain/interfaces/file_storage.py` định nghĩa abstraction; `backend/app/infra/storage/supabase_storage.py` triển khai lưu trên Supabase Storage. File được đặt bằng UUID và chỉ giữ extension gốc, tránh dùng trực tiếp filename do client cung cấp.

## Upload flow

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

Attachment tối đa 25 MB (`Attachment.MAX_SIZE_BYTES`). Avatar user/room chỉ nhận JPEG, PNG, GIF, WEBP và tối đa 5 MB. Attachment có metadata trong bảng `attachments`; avatar được lưu theo metadata/path của user hoặc room theo model/service hiện tại.

`GET /api/attachments/{attachment_id}` kiểm tra membership room rồi stream file. Ảnh/video/audio dùng `Content-Disposition: inline`; loại khác dùng `attachment`. Avatar user/room là public để `<img>` có thể tải không cần Authorization header.

## Deployment persistence

Backend dùng `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` và `SUPABASE_STORAGE_BUCKET` để truy cập bucket Supabase. Vì file nằm ngoài container nên không phụ thuộc vòng đời Docker; Compose chỉ bind mount mã nguồn `./backend:/app`.

## Considerations

`SupabaseFileStorage.save()` đọc toàn bộ upload trước khi gửi lên Supabase; giới hạn Nginx request là `30m`, lớn hơn giới hạn attachment 25 MB. Bucket cần được tạo trước trong Supabase Dashboard. Hệ thống chưa có virus scanning hoặc content sniffing độc lập được xác định từ source.

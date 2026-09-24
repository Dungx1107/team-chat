# 11. File storage

## Adapter

`backend/app/domain/interfaces/file_storage.py` định nghĩa abstraction; `backend/app/infra/storage/local_storage.py` triển khai lưu local dưới `UPLOAD_DIR`. File vật lý được đặt bằng UUID và chỉ giữ extension gốc, tránh dùng trực tiếp filename do client cung cấp. Adapter có kiểm tra path traversal.

## Upload flow

```text
Browser
 -> api.js multipart upload
 -> users.py/rooms.py/messages.py
 -> UserService/RoomService/MessageService
 -> LocalFileStorage.save()
 -> metadata AttachmentModel hoặc avatar path
 -> uploads volume
 -> response URL/id
```

Attachment tối đa 25 MB (`Attachment.MAX_SIZE_BYTES`). Avatar user/room chỉ nhận JPEG, PNG, GIF, WEBP và tối đa 5 MB. Attachment có metadata trong bảng `attachments`; avatar được lưu theo metadata/path của user hoặc room theo model/service hiện tại.

`GET /api/attachments/{attachment_id}` kiểm tra membership room rồi stream file. Ảnh/video/audio dùng `Content-Disposition: inline`; loại khác dùng `attachment`. Avatar user/room là public để `<img>` có thể tải không cần Authorization header.

## Deployment persistence

Compose đặt `UPLOAD_DIR=/app/uploads` và mount named volume `uploads:/app/uploads`. Vì vậy file sống độc lập với container backend; mã nguồn được bind mount `./backend:/app`.

## Considerations

`LocalFileStorage.save()` ghi toàn bộ upload trước khi kiểm tra giới hạn domain; giới hạn Nginx request là `30m`, lớn hơn giới hạn attachment 25 MB. Hệ thống chưa có object storage, virus scanning hoặc content sniffing độc lập được xác định từ source.

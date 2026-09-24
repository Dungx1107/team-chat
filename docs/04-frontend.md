# 4. Frontend

Frontend là static HTML/CSS/vanilla JavaScript, không có framework hay bundler. `index.html` chứa layout auth/chat, modal, input và load `css/style.css`, Tailwind CDN cùng các script JS.

| Module | Trách nhiệm thực tế |
| --- | --- |
| `js/api.js` | REST client, base URL, bearer token trong `localStorage`, refresh/retry, upload và avatar/attachment URL |
| `js/app.js` | bootstrap app, auth state, load rooms/messages/profile, đăng ký handler realtime và điều phối UI |
| `js/messages.js` | render/load/send/edit/delete/pin/reaction/file message, typing |
| `js/rooms.js` | room list, create/update/delete/join/leave, member và role UI |
| `js/profile.js` | profile form, avatar upload và cập nhật thông tin |
| `js/call.js` | call UI, `RTCPeerConnection`, offer/answer/ICE và call lifecycle |
| `js/ws.js` | WebSocket connect/reconnect/heartbeat, subscribe/unsubscribe, gửi action và dispatch event |
| `js/ui.js` | escape HTML, avatar, theme, modal/toast, format và UI helpers |
| `css/style.css` | style bổ sung cho layout/chat/scroll/indicator |

## Khởi tạo và auth

`app.js` kiểm tra token/current user trong localStorage. `api.js` gắn `Authorization: Bearer`; khi response auth hết hạn, client gọi refresh và retry một lần. Token WebSocket được truyền trong query string `/ws?token=...`.

## Quan hệ module

```text
app.js
  -> api.js        REST và token
  -> ws.js         realtime event
  -> rooms.js      room/member state
  -> messages.js   message state/render
  -> profile.js    profile/avatar
  -> call.js       call/WebRTC
  -> ui.js         shared render helpers
```

Khi chọn room, app load lịch sử qua REST rồi subscribe room trên WebSocket. Event message/room/user được `app.js` phân phối cho cache/render; call event chuyển sang `call.js`. `ui.js.escapeHtml()` được dùng trước khi ghép dữ liệu vào HTML.

## Lưu ý URL

Khi chạy qua Nginx, browser dùng HTTPS và proxy cùng origin. README cũ vẫn mô tả URL trực tiếp `:8000`/frontend `:3000`; cần ưu tiên cấu hình và logic hiện tại của `api.js` cùng `deploy/nginx/nginx.conf`.

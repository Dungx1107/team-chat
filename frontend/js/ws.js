/**
 * Kênh realtime thay cho việc gọi lại API mỗi 2 giây.
 *
 * Cách cũ: mỗi client bắn 30 request/phút vào DB dù không có tin nhắn mới.
 * Cách mới: server chủ động đẩy sự kiện xuống, client chỉ giữ một kết nối mở.
 */
const realtime = {
  socket: null,
  subscribedRoom: null,
  reconnectDelay: 1000,
  reconnectTimer: null,
  manuallyClosed: false,
  handlers: {},
  heartbeatTimer: null,

  on(event, handler) {
    (this.handlers[event] = this.handlers[event] || []).push(handler);
  },

  emit(event, data) {
    (this.handlers[event] || []).forEach((h) => {
      try {
        h(data);
      } catch (err) {
        console.error(`Lỗi xử lý sự kiện ${event}:`, err);
      }
    });
  },

  setStatus(state) {
    const el = document.getElementById("ws-status");
    if (!el) return;
    const map = {
      online: { cls: "bg-emerald-400", title: "Realtime: đang kết nối" },
      connecting: { cls: "bg-amber-400", title: "Realtime: đang kết nối lại..." },
      offline: { cls: "bg-red-500", title: "Realtime: mất kết nối" },
    };
    const s = map[state] || map.offline;
    el.className = `w-2 h-2 rounded-full shrink-0 ${s.cls}`;
    el.title = s.title;
  },

  failedAttempts: 0,

  connect() {
    const token = api.getToken();
    if (!token) return;

    this.manuallyClosed = false;
    this.setStatus("connecting");

    try {
      this.socket = new WebSocket(`${WS_URL}?token=${encodeURIComponent(token)}`);
    } catch (err) {
      console.error("Không mở được WebSocket:", err);
      this.scheduleReconnect();
      return;
    }

    this.socket.onopen = () => {
      this.reconnectDelay = 1000;
      this.failedAttempts = 0;
      this.setStatus("online");
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = setInterval(() => this.send({ action: "ping" }), 30000);
      // Mở lại kết nối thì phải đăng ký lại phòng đang xem
      if (this.subscribedRoom !== null) {
        this.subscribe(this.subscribedRoom);
      }
    };

    this.socket.onmessage = (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      this.emit(msg.event, msg.data);
    };

    this.socket.onclose = (event) => {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
      this.setStatus("offline");
      if (this.manuallyClosed) return;

      // 4001 = server từ chối vì token không hợp lệ. Nối lại cũng vô ích.
      if (event.code === 4001) {
        api.onSessionExpired();
        return;
      }

      // Chưa lần nào bắt tay được: nhiều khả năng token đã chết và bị chặn
      // ngay từ khâu handshake. Thử vài lần rồi dừng, thay vì dội request mãi.
      this.failedAttempts = (this.failedAttempts || 0) + 1;
      if (this.failedAttempts >= 4) {
        api.onSessionExpired();
        return;
      }

      this.scheduleReconnect();
    };

    this.socket.onerror = () => {
      this.setStatus("offline");
    };
  },

  scheduleReconnect() {
    if (this.reconnectTimer || this.manuallyClosed) return;
    this.setStatus("connecting");
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
      // Giãn dần khoảng chờ, tối đa 15 giây, tránh dội request khi server sập
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.6, 15000);
    }, this.reconnectDelay);
  },

  send(payload) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(payload));
      return true;
    }
    return false;
  },

  subscribe(roomId) {
    this.subscribedRoom = roomId;
    this.send({ action: "subscribe", room_id: roomId });
  },

  unsubscribe(roomId) {
    this.send({ action: "unsubscribe", room_id: roomId });
    if (this.subscribedRoom === roomId) this.subscribedRoom = null;
  },

  sendTyping(roomId) {
    this.send({ action: "typing.start", room_id: roomId });
  },

  stopTyping(roomId) {
    this.send({ action: "typing.stop", room_id: roomId });
  },

  disconnect() {
    this.manuallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
    this.subscribedRoom = null;
    this.failedAttempts = 0;
    this.setStatus("offline");
  },

  isConnected() {
    return this.socket && this.socket.readyState === WebSocket.OPEN;
  },
};

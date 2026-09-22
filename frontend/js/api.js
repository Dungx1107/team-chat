const API_HOST = `${window.location.hostname}:8000`;
const API_BASE_URL = `http://${API_HOST}/api`;
const WS_URL = `ws://${API_HOST}/ws`;

const api = {
  // ---------- Quản lý phiên ----------

  getToken() {
    return localStorage.getItem("access_token");
  },

  getRefreshToken() {
    return localStorage.getItem("refresh_token");
  },

  setSession(accessToken, refreshToken, user) {
    this.sessionExpiredNotified = false;
    localStorage.setItem("access_token", accessToken);
    if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
    if (user) localStorage.setItem("current_user", JSON.stringify(user));
  },

  updateCurrentUser(user) {
    localStorage.setItem("current_user", JSON.stringify(user));
  },

  clearSession() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("current_user");
  },

  getCurrentUser() {
    const userStr = localStorage.getItem("current_user");
    if (!userStr) return null;
    try {
      return JSON.parse(userStr);
    } catch {
      return null;
    }
  },

  // ---------- Hàm request chung ----------

  async request(endpoint, options = {}, isRetry = false) {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers = { ...(options.headers || {}) };

    // Khi gửi FormData, để trình duyệt tự đặt Content-Type kèm boundary
    const isFormData = options.body instanceof FormData;
    if (!isFormData && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    const token = this.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const response = await fetch(url, { ...options, headers });

    // Access token hết hạn -> thử làm mới một lần rồi gọi lại
    if (response.status === 401 && !isRetry) {
      const refreshed = this.getRefreshToken() ? await this.tryRefresh() : false;
      if (refreshed) return this.request(endpoint, options, true);

      // Không gia hạn được: phiên đã chết hẳn. Phải báo cho người dùng biết,
      // nếu không họ ngồi bấm gửi tin nhắn mà không hiểu vì sao không có gì xảy ra.
      this.onSessionExpired();
      const err = new Error("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại");
      err.status = 401;
      throw err;
    }

    if (response.status === 204) return true;

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      const detail = data && data.detail;
      // Lỗi validate của FastAPI trả về mảng, không phải chuỗi
      const msg = Array.isArray(detail)
        ? detail.map((d) => d.msg).join(", ")
        : detail || `Lỗi HTTP: ${response.status}`;
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }

    return data;
  },

  // Chỉ bắn một lần, tránh 5 request cùng hỏng thì hiện 5 thông báo
  sessionExpiredNotified: false,

  onSessionExpired() {
    if (this.sessionExpiredNotified) return;
    this.sessionExpiredNotified = true;
    window.dispatchEvent(new CustomEvent("session-expired"));
  },

  async tryRefresh() {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return false;
    try {
      const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      this.setSession(data.access_token, data.refresh_token, null);
      return true;
    } catch {
      return false;
    }
  },

  // ---------- Xác thực ----------

  register(payload) {
    return this.request("/auth/register", { method: "POST", body: JSON.stringify(payload) });
  },

  login(credentials) {
    return this.request("/auth/login", { method: "POST", body: JSON.stringify(credentials) });
  },

  // ---------- Phòng ----------

  getRooms() {
    return this.request("/rooms");
  },

  getRoom(roomId) {
    return this.request(`/rooms/${roomId}`);
  },

  createRoom(name, description = "", isPrivate = false) {
    return this.request("/rooms", {
      method: "POST",
      body: JSON.stringify({ name, description, is_private: isPrivate }),
    });
  },

  updateRoom(roomId, payload) {
    return this.request(`/rooms/${roomId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteRoom(roomId) {
    return this.request(`/rooms/${roomId}`, { method: "DELETE" });
  },

  joinRoom(roomId) {
    return this.request(`/rooms/${roomId}/join`, { method: "POST" });
  },

  leaveRoom(roomId) {
    return this.request(`/rooms/${roomId}/leave`, { method: "DELETE" });
  },

  // ---------- Thành viên ----------

  getMembers(roomId) {
    return this.request(`/rooms/${roomId}/members`);
  },

  addMember(roomId, userId) {
    return this.request(`/rooms/${roomId}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
  },

  removeMember(roomId, userId) {
    return this.request(`/rooms/${roomId}/members/${userId}`, { method: "DELETE" });
  },

  changeRole(roomId, userId, role) {
    return this.request(`/rooms/${roomId}/members/${userId}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    });
  },

  // ---------- Tin nhắn ----------

  getMessages(roomId, limit = 50, offset = 0) {
    return this.request(`/rooms/${roomId}/messages?limit=${limit}&offset=${offset}`);
  },

  sendMessage(roomId, content) {
    return this.request(`/rooms/${roomId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  },

  uploadFile(roomId, file, caption = "") {
    const form = new FormData();
    form.append("file", file);
    form.append("caption", caption);
    return this.request(`/rooms/${roomId}/messages/upload`, { method: "POST", body: form });
  },

  deleteMessage(messageId) {
    return this.request(`/messages/${messageId}`, { method: "DELETE" });
  },

  toggleReaction(messageId, emoji) {
    return this.request(`/messages/${messageId}/reactions`, {
      method: "POST",
      body: JSON.stringify({ emoji }),
    });
  },

  attachmentUrl(attachmentId) {
    return `${API_BASE_URL}/attachments/${attachmentId}`;
  },

  avatarUrl(userId) {
    return `${API_BASE_URL}/users/${userId}/avatar`;
  },

  // ---------- Người dùng ----------

  getMyProfile() {
    return this.request("/users/me");
  },

  updateProfile(payload) {
    return this.request("/users/me", { method: "PATCH", body: JSON.stringify(payload) });
  },

  uploadAvatar(file) {
    const form = new FormData();
    form.append("file", file);
    return this.request("/users/me/avatar", { method: "POST", body: form });
  },

  searchUsers(keyword) {
    return this.request(`/users/search?q=${encodeURIComponent(keyword)}`);
  },

  // Tệp đính kèm cần token nên không gắn thẳng vào src/href được;
  // phải tải qua fetch rồi tạo blob URL.
  async fetchBlobUrl(url) {
    const token = this.getToken();
    const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) throw new Error("Không tải được tệp");
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
};

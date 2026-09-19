const API_BASE_URL = `http://${window.location.hostname}:8000/api`;

const api = {
  // Lấy access token từ localStorage
  getToken() {
    return localStorage.getItem("access_token");
  },

  // Lưu session khi login thành công
  setSession(token, user) {
    localStorage.setItem("access_token", token);
    localStorage.setItem("current_user", JSON.stringify(user));
  },

  // Xóa session khi logout
  clearSession() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("current_user");
  },

  getCurrentUser() {
    const userStr = localStorage.getItem("current_user");
    return userStr ? JSON.parse(userStr) : null;
  },

  // Hàm request chung, tự động thêm Header và Token
  async request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {})
    };

    const token = this.getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const config = {
      ...options,
      headers
    };

    const response = await fetch(url, config);

    // Xử lý status 204 No Content (ví dụ API xóa phòng)
    if (response.status === 204) {
      return true;
    }

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      const errorMsg = (data && data.detail) ? data.detail : `Lỗi HTTP: ${response.status}`;
      throw new Error(errorMsg);
    }

    return data;
  },

  // --- Auth APIs ---
  register(userData) {
    return this.request("/auth/register", {
      method: "POST",
      body: JSON.stringify(userData)
    });
  },

  login(credentials) {
    return this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify(credentials)
    });
  },

  refreshToken(refreshToken) {
    return this.request("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken })
    });
  },

  // --- Room APIs ---
  getRooms() {
    return this.request("/rooms", { method: "GET" });
  },

  createRoom(name) {
    return this.request("/rooms", {
      method: "POST",
      body: JSON.stringify({ name })
    });
  },

  deleteRoom(roomId) {
    return this.request(`/rooms/${roomId}`, { method: "DELETE" });
  },

  // --- Message APIs ---
  getMessages(roomId) {
    return this.request(`/rooms/${roomId}/messages`, { method: "GET" });
  },

  sendMessage(roomId, content) {
    return this.request(`/rooms/${roomId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content })
    });
  }
};

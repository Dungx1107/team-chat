// ---------- Thông báo trên màn hình đăng nhập ----------

function showAlert(msg, isSuccess = false) {
  const box = document.getElementById("auth-alert");
  box.className = isSuccess
    ? "mb-4 p-3 rounded-lg text-sm bg-emerald-50 text-emerald-700 border border-emerald-200"
    : "mb-4 p-3 rounded-lg text-sm bg-red-50 text-red-700 border border-red-200";
  box.textContent = msg;
}

function clearAlert() {
  const box = document.getElementById("auth-alert");
  box.className = "hidden";
  box.textContent = "";
}

function switchAuthTab(tab) {
  clearAlert();
  const isLogin = tab === "login";
  document.getElementById("form-login").classList.toggle("hidden", !isLogin);
  document.getElementById("form-register").classList.toggle("hidden", isLogin);
  document.getElementById("tab-login-btn").className = isLogin
    ? "flex-1 py-3 font-semibold text-indigo-600 border-b-2 border-indigo-600 text-sm"
    : "flex-1 py-3 font-semibold text-slate-400 text-sm";
  document.getElementById("tab-register-btn").className = isLogin
    ? "flex-1 py-3 font-semibold text-slate-400 text-sm"
    : "flex-1 py-3 font-semibold text-indigo-600 border-b-2 border-indigo-600 text-sm";
}

// ---------- Đăng ký / Đăng nhập / Đăng xuất ----------

async function onRegisterSubmit(event) {
  event.preventDefault();
  clearAlert();

  try {
    await api.register({
      first_name: document.getElementById("reg-firstname").value.trim(),
      last_name: document.getElementById("reg-lastname").value.trim(),
      username: document.getElementById("reg-username").value.trim(),
      email: document.getElementById("reg-email").value.trim(),
      password: document.getElementById("reg-password").value,
    });
    showAlert("Đăng ký thành công! Hãy chuyển sang tab Đăng nhập.", true);
    document.getElementById("form-register").reset();
    setTimeout(() => switchAuthTab("login"), 1200);
  } catch (err) {
    showAlert(err.message);
  }
}

async function onLoginSubmit(event) {
  event.preventDefault();
  clearAlert();

  try {
    const data = await api.login({
      email: document.getElementById("login-email").value.trim(),
      password: document.getElementById("login-password").value,
    });
    api.setSession(data.access_token, data.refresh_token, data.user);
    document.getElementById("form-login").reset();
    await enterChat();
  } catch (err) {
    showAlert(err.message);
  }
}

// Phiên hết hạn giữa chừng: đưa về màn hình đăng nhập kèm lời giải thích,
// thay vì để người dùng bấm mãi mà không có phản hồi.
window.addEventListener("session-expired", () => {
  const wasInChat = !document.getElementById("chat-view").classList.contains("hidden");
  handleLogout();
  if (wasInChat) {
    showAlert("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
  }
});

function handleLogout() {
  realtime.disconnect();
  resetChatArea();
  roomsCache = [];
  membersCache = [];
  api.clearSession();
  showAuthView();
}

// ---------- Chuyển màn hình ----------

function showAuthView() {
  document.getElementById("auth-view").classList.remove("hidden");
  document.getElementById("chat-view").classList.add("hidden");
  switchAuthTab("login");
}

async function enterChat() {
  document.getElementById("auth-view").classList.add("hidden");
  document.getElementById("chat-view").classList.remove("hidden");

  // Lấy hồ sơ mới nhất từ server thay vì tin vào bản lưu trong localStorage
  let user = api.getCurrentUser();
  try {
    user = await api.getMyProfile();
    api.updateCurrentUser(user);
  } catch (err) {
    if (err.status === 401) {
      handleLogout();
      return;
    }
  }

  renderMyAvatarBar(user);
  registerRealtimeHandlers();
  realtime.connect();
  await loadRooms();
}

// ---------- Xử lý sự kiện realtime ----------

function registerRealtimeHandlers() {
  if (registerRealtimeHandlers.done) return;
  registerRealtimeHandlers.done = true;

  realtime.on("message.created", async (data) => {
    if (!currentRoom || data.room_id !== currentRoom.id) {
      // Tin nhắn ở phòng khác: chỉ báo nhẹ, không cắt ngang
      const room = roomsCache.find((r) => r.id === data.room_id);
      const me = api.getCurrentUser();
      if (room && me && data.user_id !== me.id) {
        toast(`${data.sender_name || "Ai đó"} nhắn trong # ${room.name}`);
      }
      return;
    }

    if (messagesCache.some((m) => m.id === data.id)) return;
    messagesCache.push(data);
    renderMessages();
    await hydrateSecureMedia();

    // Người vừa gửi thì thôi báo "đang soạn tin"
    delete typingTimers[data.user_id];
    renderTypingIndicator();
  });

  realtime.on("message.deleted", (data) => {
    if (!currentRoom || data.room_id !== currentRoom.id) return;
    const msg = messagesCache.find((m) => m.id === data.id);
    if (msg) {
      msg.is_deleted = true;
      msg.content = "";
      renderMessages(true);
    }
  });

  realtime.on("reaction.updated", (data) => {
    if (!currentRoom || data.room_id !== currentRoom.id) return;
    applyReactionUpdate(data);
  });

  realtime.on("user.typing", (data) => {
    if (!currentRoom || data.room_id !== currentRoom.id) return;
    showTyping(data.user_id);
  });

  realtime.on("room.member_joined", async (data) => {
    if (currentRoom && data.room_id === currentRoom.id) {
      await loadMembers();
      if (membersPanelOpen) renderMembers();
    }
    const me = api.getCurrentUser();
    // Mình vừa được mời vào phòng mới -> nạp lại danh sách phòng
    if (me && data.user_id === me.id) await loadRooms();
  });

  realtime.on("room.member_left", async (data) => {
    const me = api.getCurrentUser();
    if (me && data.user_id === me.id) {
      if (currentRoom && data.room_id === currentRoom.id) {
        toast("Bạn đã bị xóa khỏi phòng này", "error");
        resetChatArea();
      }
      await loadRooms();
      return;
    }
    if (currentRoom && data.room_id === currentRoom.id) {
      await loadMembers();
      if (membersPanelOpen) renderMembers();
    }
  });

  realtime.on("room.role_changed", async (data) => {
    const me = api.getCurrentUser();
    if (currentRoom && data.room_id === currentRoom.id) {
      if (me && data.user_id === me.id) {
        currentRoom.my_role = data.role;
        updateRoomHeader();
        renderMessages(true);
        toast(
          data.role === "ADMIN"
            ? "Bạn vừa được phong làm quản trị viên"
            : "Vai trò của bạn đã thay đổi",
          "success"
        );
      }
      await loadMembers();
      if (membersPanelOpen) renderMembers();
    }
  });

  realtime.on("room.updated", async (data) => {
    await loadRooms();
    if (currentRoom && data.id === currentRoom.id) {
      currentRoom = { ...currentRoom, ...data };
      updateRoomHeader();
    }
  });

  realtime.on("room.deleted", async (data) => {
    if (currentRoom && data.id === currentRoom.id) {
      toast("Phòng này vừa bị xóa", "error");
      resetChatArea();
    }
    await loadRooms();
  });

  realtime.on("error", (data) => {
    if (data && data.detail) toast(data.detail, "error");
  });
}

// ---------- Khởi động ----------

document.addEventListener("DOMContentLoaded", async () => {
  if (api.getToken() && api.getCurrentUser()) {
    await enterChat();
  } else {
    showAuthView();
  }
});

// Quay lại tab sau một lúc: nối lại realtime nếu đã rớt
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && api.getToken() && !realtime.isConnected()) {
    realtime.connect();
  }
});

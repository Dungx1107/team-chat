// ---------- Thông báo trên màn hình đăng nhập ----------

function showAlert(msg, isSuccess = false) {
  const box = document.getElementById("auth-alert");
  box.className = isSuccess
    ? "mb-4 p-3 rounded-lg text-sm bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
    : "mb-4 p-3 rounded-lg text-sm bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800";
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
  if (callUI.isBusy()) callUI.hangup();
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
    const message = data.message || data;
    data = message;
    updateRoomSummaryFromMessage(data, !currentRoom || data.room_id !== currentRoom.id);
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
    renderMessages(true);
    await hydrateSecureMedia();

    // Người vừa gửi thì thôi báo "đang soạn tin"
    delete typingTimers[data.user_id];
    renderTypingIndicator();
  });

  realtime.on("message.deleted", (data) => {
    if (!currentRoom || data.room_id !== currentRoom.id) return;
    const msg = messagesCache.find((m) => m.id === data.message_id || m.id === data.id);
    if (msg) {
      msg.is_deleted = true;
      msg.content = "";
      renderMessages(true);
    }
  });

  realtime.on("message.reaction", (data) => {
    if (!currentRoom || data.room_id !== currentRoom.id) return;
    applyReactionUpdate(data);
  });

  realtime.on("typing.start", (data) => {
    if (!currentRoom || data.room_id !== currentRoom.id) return;
    showTyping(data.user_id);
  });

  realtime.on("typing.stop", (data) => {
    delete typingTimers[data.user_id];
    renderTypingIndicator();
  });

  realtime.on("message.updated", (data) => {
    const updated = data.message || data;
    const index = messagesCache.findIndex((m) => m.id === updated.id);
    if (index < 0) return;
    messagesCache[index] = updated;
    renderMessages(true);
  });

  realtime.on("message.pinned", (data) => {
    if (!currentRoom || data.room_id !== currentRoom.id) return;
    const incoming = data.message || {};
    const msg = messagesCache.find((m) => m.id === data.message_id);
    if (msg) {
      Object.assign(msg, incoming, {
        pinned: data.pinned,
        pinned_at: data.pinned_at,
        pinned_by: data.pinned_by,
      });
      updatePinnedCache(msg);
    } else if (data.pinned && incoming.id) {
      updatePinnedCache({ ...incoming, pinned: true, pinned_at: data.pinned_at, pinned_by: data.pinned_by });
    } else {
      pinnedMessagesCache = pinnedMessagesCache.filter((item) => item.id !== data.message_id);
      renderPinnedMessages();
    }
    renderMessages(true);
  });

  realtime.on("user.updated", (data) => {
    const user = data.user || data;
    avatarVersions[user.id] = Date.now();
    const current = api.getCurrentUser();
    if (current && Number(current.id) === Number(user.id)) {
      api.updateCurrentUser({ ...current, ...user });
      renderMyAvatarBar({ ...current, ...user });
    }
    if (currentRoom) {
      messagesCache.forEach((message) => {
        if (Number(message.user_id) === Number(user.id)) {
          message.avatar_url = user.avatar_url;
          message.sender_name = user.full_name;
        }
      });
      renderMessages(true);
      if (membersPanelOpen) renderMembers();
    }
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

  realtime.on("room.summary_updated", (data) => {
    if (data.last_message) updateRoomSummaryFromMessage(data.last_message, false);
  });

  realtime.on("room.avatar_updated", (data) => {
    const room = roomsCache.find((item) => item.id === data.room_id);
    if (!room) return;
    room.avatar_url = data.avatar_url;
    roomAvatarVersions[room.id] = Date.now();
    if (currentRoom && currentRoom.id === room.id) {
      currentRoom.avatar_url = data.avatar_url;
      updateRoomHeader();
    }
    renderRoomList();
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
  syncThemeIcons();
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

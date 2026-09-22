let currentRoom = null;
let roomsCache = [];
let membersCache = [];
let membersPanelOpen = false;
let roomSearchQuery = "";
let roomSearchTimer = null;

// ---------- Danh sách phòng ----------

async function loadRooms() {
  try {
    roomsCache = await api.getRooms();
    renderRoomList();
  } catch (err) {
    console.error("Lỗi tải phòng:", err);
  }
}

function renderRoomList() {
  const container = document.getElementById("room-list-container");
  const visibleRooms = roomsCache.filter((room) => !roomSearchQuery || room.name.toLowerCase().includes(roomSearchQuery));
  const countLabel = document.getElementById("room-count-label");
  if (countLabel) countLabel.textContent = `${visibleRooms.length}/${roomsCache.length}`;

  if (!visibleRooms.length) {
    container.innerHTML = `<p class="text-[11px] text-slate-500 p-3 text-center leading-relaxed">
      Chưa có phòng nào.<br />Bấm dấu + để tạo phòng mới.
    </p>`;
    return;
  }

  container.innerHTML = visibleRooms
    .map((r) => {
      const active = currentRoom && currentRoom.id === r.id;
      const joined = !!r.my_role;
      const unread = Number(r.unread_count || 0);
      const preview = roomPreview(r);

      return `<button onclick="selectRoomById(${r.id})"
        class="room-list-item w-full text-left px-3 py-2.5 rounded-lg transition flex items-center gap-3 ${
          active
            ? "bg-indigo-100 dark:bg-indigo-900/40 text-indigo-950 dark:text-indigo-100 border-l-[3px] border-indigo-600"
            : "text-slate-700 dark:text-slate-300 hover:bg-white/80 dark:hover:bg-white/10 hover:text-slate-900 dark:hover:text-slate-200 border-l-[3px] border-transparent"
        }">
        <span class="shrink-0 relative">${renderRoomAvatar(r, 48)}${r.theme_color ? `<i class="absolute -left-1 top-1 w-2 h-2 rounded-full border border-white dark:border-slate-900" style="background:${escapeHtml(r.theme_color)}"></i>` : ""}</span>
        <span class="min-w-0 flex-1">
          <span class="flex items-center gap-1.5"><span class="block text-sm truncate ${active || unread ? "font-bold" : "font-semibold"}">${r.is_private ? "🔒 " : ""}${escapeHtml(r.name)}</span>${unread ? `<span class="shrink-0 min-w-5 px-1.5 py-0.5 rounded-full bg-indigo-500 text-white text-[10px] text-center">${unread > 99 ? "99+" : unread}</span>` : ""}</span>
          <span class="block text-[11px] truncate ${active ? "text-indigo-700 dark:text-indigo-300" : "text-slate-500 dark:text-slate-400"}">${escapeHtml(preview)}</span>
        </span>
        <span class="shrink-0 self-start text-[10px] ${active ? "text-indigo-700 dark:text-indigo-300" : "text-slate-400 dark:text-slate-500"}">${formatRoomTime(r.last_message?.created_at)}</span>
      </button>`;
    })
    .join("");
}

function roomPreview(room) {
  const last = room.last_message;
  if (!last) return "Chưa có tin nhắn";
  const sender = last.sender_name || "Ai đó";
  if (last.is_deleted) return `${sender}: Tin nhắn đã được thu hồi`;
  if (last.type === "FILE" && last.attachment_filename) return `${sender}: 📎 ${last.attachment_filename}`;
  return `${sender}: ${last.content || "📷 Hình ảnh"}`;
}

function onRoomSearchInput(event) {
  roomSearchQuery = event.target.value.trim().toLowerCase();
  renderRoomList();
  clearTimeout(roomSearchTimer);
  const suggestions = document.getElementById("room-search-suggestions");
  if (!event.target.value.trim()) {
    suggestions?.classList.add("hidden");
    return;
  }
  roomSearchTimer = setTimeout(async () => {
    try {
      const users = await api.searchUsers(event.target.value.trim());
      if (!users.length || !suggestions) return suggestions?.classList.add("hidden");
      suggestions.innerHTML = users.slice(0, 5).map((user) => `<button type="button" onclick="openUserProfile(${user.id})" class="w-full flex items-center gap-2 p-2 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-left">${renderAvatar(user, 28)}<span class="min-w-0"><span class="block text-xs font-semibold truncate">${escapeHtml(user.full_name)}</span><span class="block text-[10px] text-slate-500 truncate">@${escapeHtml(user.username)}</span></span></button>`).join("");
      suggestions.classList.remove("hidden");
    } catch {
      suggestions?.classList.add("hidden");
    }
  }, 300);
}

function selectRoomById(roomId) {
  const room = roomsCache.find((r) => r.id === roomId);
  if (room) selectRoom(room);
}

async function selectRoom(room) {
  // Rời kênh realtime của phòng cũ
  if (currentRoom && currentRoom.id !== room.id) {
    realtime.unsubscribe(currentRoom.id);
  }

  currentRoom = room;
  room.unread_count = 0;
  typingTimers = {};
  renderTypingIndicator();
  renderRoomList();
  updateRoomHeader();

  // Phòng công khai chưa tham gia: vào luôn cho tiện
  if (!room.my_role && !room.is_private) {
    try {
      await api.joinRoom(room.id);
      const fresh = await api.getRoom(room.id);
      currentRoom = fresh;
      const idx = roomsCache.findIndex((r) => r.id === room.id);
      if (idx >= 0) roomsCache[idx] = fresh;
      renderRoomList();
      updateRoomHeader();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  realtime.subscribe(room.id);

  await loadMessages();
  await loadPinnedMessages();
  await hydrateSecureMedia();
  await loadMembers();
  renderPinnedMessages();

  const input = document.getElementById("input-message");
  input.disabled = false;
  document.getElementById("btn-send-message").disabled = false;
  document.getElementById("btn-attach").disabled = false;
  input.focus();
}

function updateRoomHeader() {
  if (!currentRoom) return;
  const me = api.getCurrentUser();
  const icon = currentRoom.is_private ? "🔒" : "#";

  document.getElementById("active-room-name").textContent = `${icon} ${currentRoom.name}`;
  const roomAvatar = document.getElementById("active-room-avatar");
  if (roomAvatar) roomAvatar.innerHTML = renderRoomAvatar(currentRoom, 40);

  const parts = [];
  if (currentRoom.description) parts.push(currentRoom.description);
  parts.push(currentRoom.is_private ? "Phòng riêng tư" : "Phòng công khai");
  if (currentRoom.my_role) parts.push(ROLE_LABELS[currentRoom.my_role].text);
  document.getElementById("active-room-desc").textContent = parts.join(" · ");

  const isOwner = me && currentRoom.owner_id === me.id;
  const canManage = ["OWNER", "ADMIN"].includes(currentRoom.my_role);

  document.getElementById("btn-toggle-members").classList.remove("hidden");
  document.getElementById("member-count-badge").textContent = currentRoom.member_count ?? 0;

  toggleEl("btn-room-settings", canManage);
  toggleEl("btn-delete-room", isOwner);
  toggleEl("btn-leave-room", !!currentRoom.my_role && !isOwner);
  toggleEl("btn-add-member", canManage);
}

function toggleEl(id, show) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle("hidden", !show);
}

// ---------- Tạo phòng ----------

function openCreateRoomModal() {
  openModal(`
    <div class="p-5">
      <h3 class="font-bold text-lg text-slate-900 dark:text-slate-100 mb-4">Tạo phòng mới</h3>
      <form onsubmit="onCreateRoom(event)" class="space-y-4">
        <div>
          <label class="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">Tên phòng</label>
          <input id="new-room-name" required maxlength="150" autofocus
                 class="w-full px-3.5 py-2.5 border border-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                 placeholder="ví dụ: Thảo luận đồ án" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">Mô tả <span class="font-normal text-slate-400 dark:text-slate-500">(tùy chọn)</span></label>
          <input id="new-room-desc" maxlength="300"
                 class="w-full px-3.5 py-2.5 border border-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                 placeholder="Phòng này dùng để làm gì?" />
        </div>
        <label class="flex items-start gap-2.5 p-3 border border-slate-200 dark:border-slate-700 rounded-lg cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800">
          <input type="checkbox" id="new-room-private" class="mt-0.5" />
          <span>
            <span class="block text-sm font-medium text-slate-800 dark:text-slate-200">🔒 Phòng riêng tư</span>
            <span class="block text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">
              Chỉ người được mời mới thấy và vào được phòng này.
            </span>
          </span>
        </label>
        <div class="flex gap-2 pt-1">
          <button type="button" onclick="closeModal()"
                  class="flex-1 py-2.5 border border-slate-200 dark:border-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800">Hủy</button>
          <button type="submit"
                  class="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold">Tạo phòng</button>
        </div>
      </form>
    </div>
  `);
}

async function onCreateRoom(event) {
  event.preventDefault();
  const name = document.getElementById("new-room-name").value.trim();
  const desc = document.getElementById("new-room-desc").value.trim();
  const isPrivate = document.getElementById("new-room-private").checked;
  if (!name) return;

  try {
    const room = await api.createRoom(name, desc, isPrivate);
    closeModal();
    await loadRooms();
    await selectRoom(room);
    toast(`Đã tạo phòng "${room.name}"`, "success");
  } catch (err) {
    toast("Không tạo được phòng: " + err.message, "error");
  }
}

// ---------- Cài đặt phòng ----------

function openRoomSettingsModal() {
  if (!currentRoom) return;
  openModal(`
    <div class="p-5">
      <h3 class="font-bold text-lg text-slate-900 dark:text-slate-100 mb-4">Cài đặt phòng</h3>
      <div class="flex items-center gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50">
        ${renderRoomAvatar(currentRoom, 52)}
        <div class="min-w-0 flex-1">
          <div class="text-xs font-semibold text-slate-800 dark:text-slate-200">Ảnh đại diện phòng</div>
          <div class="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">JPEG, PNG, GIF hoặc WEBP · tối đa 5MB</div>
          <button type="button" onclick="document.getElementById('room-avatar-input').click()" class="mt-2 px-2.5 py-1.5 text-xs border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-white dark:hover:bg-slate-700">Đổi ảnh</button>
          <input id="room-avatar-input" type="file" accept="image/*" class="hidden" onchange="onRoomAvatarSelected(event)" />
        </div>
      </div>
      <form onsubmit="onUpdateRoom(event)" class="space-y-4">
        <div>
          <label class="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">Tên phòng</label>
          <input id="edit-room-name" required maxlength="150" value="${escapeHtml(currentRoom.name)}"
                 class="w-full px-3.5 py-2.5 border border-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">Mô tả</label>
          <input id="edit-room-desc" maxlength="300" value="${escapeHtml(currentRoom.description || "")}"
                 class="w-full px-3.5 py-2.5 border border-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div class="text-[11px] text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/50 rounded-lg p-3 leading-relaxed">
          Loại phòng: <strong>${currentRoom.is_private ? "Riêng tư 🔒" : "Công khai #"}</strong><br />
          Không thể đổi loại phòng sau khi đã tạo.
        </div>
        <div class="flex gap-2">
          <button type="button" onclick="closeModal()"
                  class="flex-1 py-2.5 border border-slate-200 dark:border-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800">Hủy</button>
          <button type="submit"
                  class="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold">Lưu</button>
        </div>
      </form>
    </div>
  `);
}

async function onRoomAvatarSelected(event) {
  const file = event.target.files[0];
  if (!file || !currentRoom) return;
  try {
    const updated = await api.uploadRoomAvatar(currentRoom.id, file);
    currentRoom = { ...currentRoom, ...updated };
    roomAvatarVersions[currentRoom.id] = Date.now();
    await loadRooms();
    updateRoomHeader();
    openRoomSettingsModal();
    toast("Đã cập nhật avatar phòng", "success");
  } catch (err) {
    toast(err.status === 403 ? "Không có quyền" : err.message, "error");
  }
}

async function onUpdateRoom(event) {
  event.preventDefault();
  try {
    const updated = await api.updateRoom(currentRoom.id, {
      name: document.getElementById("edit-room-name").value.trim(),
      description: document.getElementById("edit-room-desc").value.trim(),
    });
    currentRoom = { ...currentRoom, ...updated };
    closeModal();
    await loadRooms();
    updateRoomHeader();
    toast("Đã cập nhật phòng", "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

async function onDeleteCurrentRoom() {
  if (!currentRoom) return;
  if (!confirm(`Xóa vĩnh viễn phòng "${currentRoom.name}"?\nToàn bộ tin nhắn sẽ mất.`)) return;

  try {
    await api.deleteRoom(currentRoom.id);
    resetChatArea();
    await loadRooms();
    toast("Đã xóa phòng", "success");
  } catch (err) {
    toast("Không xóa được: " + err.message, "error");
  }
}

async function onLeaveCurrentRoom() {
  if (!currentRoom) return;
  if (!confirm(`Rời khỏi phòng "${currentRoom.name}"?`)) return;

  try {
    await api.leaveRoom(currentRoom.id);
    resetChatArea();
    await loadRooms();
    toast("Đã rời phòng", "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

function resetChatArea() {
  if (currentRoom) realtime.unsubscribe(currentRoom.id);
  currentRoom = null;
  messagesCache = [];
  pinnedMessagesCache = [];
  document.getElementById("pinned-panel")?.classList.add("hidden");

  document.getElementById("active-room-name").textContent = "Chưa chọn phòng nào";
  document.getElementById("active-room-desc").textContent =
    "Chọn một phòng ở danh sách bên trái để bắt đầu trò chuyện";
  document.getElementById("messages-scroll-area").innerHTML =
    `<div class="text-center text-slate-400 dark:text-slate-500 text-xs mt-16">Chọn một phòng để xem tin nhắn</div>`;

  ["btn-delete-room", "btn-leave-room", "btn-room-settings", "btn-toggle-members", "btn-add-member"]
    .forEach((id) => toggleEl(id, false));

  document.getElementById("input-message").disabled = true;
  document.getElementById("btn-send-message").disabled = true;
  document.getElementById("btn-attach").disabled = true;
  document.getElementById("members-panel").classList.add("hidden");
  membersPanelOpen = false;
  clearPendingFile();
}

function updateRoomSummaryFromMessage(message, incrementUnread = false) {
  const room = roomsCache.find((item) => item.id === message.room_id);
  if (!room) return;
  room.last_message = {
    id: message.id,
    content: message.content || "",
    sender_name: message.sender_name || message.sender?.full_name || "Ai đó",
    created_at: message.created_at,
    type: message.type || message.message_type,
    is_deleted: message.is_deleted,
    attachment_filename: message.attachment?.filename || null,
  };
  if (incrementUnread) room.unread_count = Number(room.unread_count || 0) + 1;
  renderRoomList();
}

// ---------- Thành viên ----------

function toggleMembersPanel() {
  membersPanelOpen = !membersPanelOpen;
  const panel = document.getElementById("members-panel");
  panel.classList.toggle("hidden", !membersPanelOpen);
  panel.classList.toggle("flex", membersPanelOpen);
  if (membersPanelOpen) loadMembers();
}

async function loadMembers() {
  if (!currentRoom) return;
  try {
    membersCache = await api.getMembers(currentRoom.id);
    document.getElementById("member-count-badge").textContent = membersCache.length;
    if (membersPanelOpen) renderMembers();
  } catch (err) {
    membersCache = [];
  }
}

function renderMembers() {
  const me = api.getCurrentUser();
  const myId = me ? me.id : null;
  const isOwner = currentRoom && currentRoom.my_role === "OWNER";
  const canManage = currentRoom && ["OWNER", "ADMIN"].includes(currentRoom.my_role);

  document.getElementById("members-list").innerHTML = membersCache
    .map((m) => {
      const isSelf = m.user_id === myId;
      const canActOn = canManage && !isSelf && m.role !== "OWNER";

      return `<div class="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 group">
        <div class="shrink-0">${renderAvatar(m, 32)}</div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5">
            <span class="text-xs font-medium text-slate-800 dark:text-slate-200 truncate">${escapeHtml(m.full_name)}</span>
            ${isSelf ? `<span class="text-[10px] text-slate-400 dark:text-slate-500">(bạn)</span>` : ""}
          </div>
          <div class="flex items-center gap-1.5 mt-0.5">
            ${roleBadge(m.role)}
            ${m.is_online ? `<span class="text-[10px] text-emerald-600">● online</span>` : ""}
          </div>
        </div>
        ${
          !isSelf
            ? `<div class="shrink-0 flex items-center gap-0.5 md:opacity-0 md:group-hover:opacity-100 transition">
                 <button onclick="callUI.startCall(${m.user_id}, 'AUDIO')" ${m.is_online ? "" : "disabled"}
                   title="${m.is_online ? "Gọi thoại" : "Người này đang offline"}"
                   class="w-6 h-6 flex items-center justify-center rounded hover:bg-emerald-100 dark:hover:bg-emerald-900/40 text-sm disabled:opacity-30 disabled:cursor-not-allowed">📞</button>
                 <button onclick="callUI.startCall(${m.user_id}, 'VIDEO')" ${m.is_online ? "" : "disabled"}
                   title="${m.is_online ? "Gọi video" : "Người này đang offline"}"
                   class="w-6 h-6 flex items-center justify-center rounded hover:bg-emerald-100 dark:hover:bg-emerald-900/40 text-sm disabled:opacity-30 disabled:cursor-not-allowed">🎥</button>
               </div>`
            : ""
        }
        ${
          canActOn
            ? `<button onclick="openMemberActions(${m.user_id})"
                 class="shrink-0 opacity-0 group-hover:opacity-100 w-6 h-6 flex items-center justify-center rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 transition">⋯</button>`
            : ""
        }
      </div>`;
    })
    .join("");
}

function openMemberActions(userId) {
  const member = membersCache.find((m) => m.user_id === userId);
  if (!member) return;
  const isOwner = currentRoom.my_role === "OWNER";

  openModal(`
    <div class="p-5">
      <div class="flex items-center gap-3 mb-4">
        ${renderAvatar(member, 44)}
        <div class="min-w-0">
          <div class="font-bold text-slate-900 dark:text-slate-100 truncate">${escapeHtml(member.full_name)}</div>
          <div class="text-xs text-slate-500 dark:text-slate-400">@${escapeHtml(member.username)}</div>
        </div>
      </div>

      <div class="space-y-2">
        ${
          isOwner
            ? member.role === "ADMIN"
              ? `<button onclick="onChangeRole(${userId}, 'MEMBER')"
                   class="w-full text-left px-3.5 py-2.5 border border-slate-200 dark:border-slate-700 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-slate-800">
                   ⬇️ Giáng xuống Thành viên
                 </button>`
              : `<button onclick="onChangeRole(${userId}, 'ADMIN')"
                   class="w-full text-left px-3.5 py-2.5 border border-slate-200 dark:border-slate-700 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-slate-800">
                   ⬆️ Phong làm Quản trị viên
                 </button>`
            : ""
        }
        <button onclick="onRemoveMember(${userId})"
                class="w-full text-left px-3.5 py-2.5 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 rounded-lg text-sm hover:bg-red-50 dark:hover:bg-red-900/30">
          🚫 Xóa khỏi phòng
        </button>
        <button onclick="closeModal()"
                class="w-full px-3.5 py-2.5 border border-slate-200 dark:border-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800">
          Đóng
        </button>
      </div>
    </div>
  `);
}

async function onChangeRole(userId, role) {
  try {
    await api.changeRole(currentRoom.id, userId, role);
    closeModal();
    await loadMembers();
    renderMembers();
    toast(role === "ADMIN" ? "Đã phong quản trị viên" : "Đã giáng xuống thành viên", "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

async function onRemoveMember(userId) {
  if (!confirm("Xóa người này khỏi phòng?")) return;
  try {
    await api.removeMember(currentRoom.id, userId);
    closeModal();
    await loadMembers();
    renderMembers();
    toast("Đã xóa khỏi phòng", "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

// ---------- Mời thành viên ----------

function openAddMemberModal() {
  openModal(`
    <div class="p-5">
      <h3 class="font-bold text-lg text-slate-900 dark:text-slate-100 mb-1">Thêm thành viên</h3>
      <p class="text-xs text-slate-500 dark:text-slate-400 mb-4">Tìm theo tên, username hoặc email.</p>
      <input id="user-search-input" oninput="onSearchUsers(this.value)" autofocus
             class="w-full px-3.5 py-2.5 border border-slate-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
             placeholder="Nhập để tìm..." />
      <div id="user-search-results" class="mt-3 space-y-1 max-h-64 overflow-y-auto scroll-thin"></div>
      <button onclick="closeModal()"
              class="w-full mt-4 py-2.5 border border-slate-200 dark:border-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800">Đóng</button>
    </div>
  `);
}

let searchDebounce = null;

function onSearchUsers(keyword) {
  clearTimeout(searchDebounce);
  const box = document.getElementById("user-search-results");

  if (!keyword.trim()) {
    box.innerHTML = "";
    return;
  }

  // Chờ người dùng ngừng gõ rồi mới gọi API
  searchDebounce = setTimeout(async () => {
    try {
      const users = await api.searchUsers(keyword);
      const existingIds = new Set(membersCache.map((m) => m.user_id));
      const candidates = users.filter((u) => !existingIds.has(u.id));

      if (!candidates.length) {
        box.innerHTML = `<p class="text-xs text-slate-400 dark:text-slate-500 text-center py-3">Không tìm thấy ai phù hợp</p>`;
        return;
      }

      box.innerHTML = candidates
        .map(
          (u) => `<button onclick="onAddMember(${u.id})"
            class="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 text-left">
            ${renderAvatar(u, 32)}
            <span class="min-w-0 flex-1">
              <span class="block text-xs font-medium text-slate-800 dark:text-slate-200 truncate">${escapeHtml(u.full_name)}</span>
              <span class="block text-[11px] text-slate-400 dark:text-slate-500 truncate">@${escapeHtml(u.username)}</span>
            </span>
            <span class="shrink-0 text-indigo-600 text-lg leading-none">+</span>
          </button>`
        )
        .join("");
    } catch (err) {
      box.innerHTML = `<p class="text-xs text-red-500 text-center py-3">${escapeHtml(err.message)}</p>`;
    }
  }, 300);
}

async function onAddMember(userId) {
  try {
    await api.addMember(currentRoom.id, userId);
    await loadMembers();
    renderMembers();
    onSearchUsers(document.getElementById("user-search-input").value);
    toast("Đã thêm vào phòng", "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

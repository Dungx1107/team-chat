let currentRoom = null;
let roomsCache = [];
let membersCache = [];
let membersPanelOpen = false;

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

  if (!roomsCache.length) {
    container.innerHTML = `<p class="text-[11px] text-slate-500 p-3 text-center leading-relaxed">
      Chưa có phòng nào.<br />Bấm dấu + để tạo phòng mới.
    </p>`;
    return;
  }

  container.innerHTML = roomsCache
    .map((r) => {
      const active = currentRoom && currentRoom.id === r.id;
      const icon = r.is_private ? "🔒" : "#";
      const joined = !!r.my_role;

      return `<button onclick="selectRoomById(${r.id})"
        class="w-full text-left px-2.5 py-1.5 rounded-lg transition flex items-center gap-2 ${
          active ? "bg-indigo-600 text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
        }">
        <span class="shrink-0 text-xs ${active ? "text-white/70" : "text-slate-500"}">${icon}</span>
        <span class="min-w-0 flex-1">
          <span class="block text-sm truncate ${active ? "font-semibold" : ""}">${escapeHtml(r.name)}</span>
        </span>
        ${
          !joined
            ? `<span class="shrink-0 text-[9px] px-1 py-0.5 rounded ${
                active ? "bg-white/20" : "bg-slate-700 text-slate-400"
              }">chưa vào</span>`
            : ""
        }
      </button>`;
    })
    .join("");
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
  await hydrateSecureMedia();
  await loadMembers();

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
      <h3 class="font-bold text-lg text-slate-900 mb-4">Tạo phòng mới</h3>
      <form onsubmit="onCreateRoom(event)" class="space-y-4">
        <div>
          <label class="block text-xs font-semibold text-slate-600 mb-1.5">Tên phòng</label>
          <input id="new-room-name" required maxlength="150" autofocus
                 class="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                 placeholder="ví dụ: Thảo luận đồ án" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-600 mb-1.5">Mô tả <span class="font-normal text-slate-400">(tùy chọn)</span></label>
          <input id="new-room-desc" maxlength="300"
                 class="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                 placeholder="Phòng này dùng để làm gì?" />
        </div>
        <label class="flex items-start gap-2.5 p-3 border border-slate-200 rounded-lg cursor-pointer hover:bg-slate-50">
          <input type="checkbox" id="new-room-private" class="mt-0.5" />
          <span>
            <span class="block text-sm font-medium text-slate-800">🔒 Phòng riêng tư</span>
            <span class="block text-[11px] text-slate-500 mt-0.5 leading-relaxed">
              Chỉ người được mời mới thấy và vào được phòng này.
            </span>
          </span>
        </label>
        <div class="flex gap-2 pt-1">
          <button type="button" onclick="closeModal()"
                  class="flex-1 py-2.5 border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50">Hủy</button>
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
      <h3 class="font-bold text-lg text-slate-900 mb-4">Cài đặt phòng</h3>
      <form onsubmit="onUpdateRoom(event)" class="space-y-4">
        <div>
          <label class="block text-xs font-semibold text-slate-600 mb-1.5">Tên phòng</label>
          <input id="edit-room-name" required maxlength="150" value="${escapeHtml(currentRoom.name)}"
                 class="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-600 mb-1.5">Mô tả</label>
          <input id="edit-room-desc" maxlength="300" value="${escapeHtml(currentRoom.description || "")}"
                 class="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div class="text-[11px] text-slate-500 bg-slate-50 rounded-lg p-3 leading-relaxed">
          Loại phòng: <strong>${currentRoom.is_private ? "Riêng tư 🔒" : "Công khai #"}</strong><br />
          Không thể đổi loại phòng sau khi đã tạo.
        </div>
        <div class="flex gap-2">
          <button type="button" onclick="closeModal()"
                  class="flex-1 py-2.5 border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50">Hủy</button>
          <button type="submit"
                  class="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold">Lưu</button>
        </div>
      </form>
    </div>
  `);
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

  document.getElementById("active-room-name").textContent = "Chưa chọn phòng nào";
  document.getElementById("active-room-desc").textContent =
    "Chọn một phòng ở danh sách bên trái để bắt đầu trò chuyện";
  document.getElementById("messages-scroll-area").innerHTML =
    `<div class="text-center text-slate-400 text-xs mt-16">Chọn một phòng để xem tin nhắn</div>`;

  ["btn-delete-room", "btn-leave-room", "btn-room-settings", "btn-toggle-members", "btn-add-member"]
    .forEach((id) => toggleEl(id, false));

  document.getElementById("input-message").disabled = true;
  document.getElementById("btn-send-message").disabled = true;
  document.getElementById("btn-attach").disabled = true;
  document.getElementById("members-panel").classList.add("hidden");
  membersPanelOpen = false;
  clearPendingFile();
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

      return `<div class="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-slate-50 group">
        <div class="shrink-0">${renderAvatar(m, 32)}</div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5">
            <span class="text-xs font-medium text-slate-800 truncate">${escapeHtml(m.full_name)}</span>
            ${isSelf ? `<span class="text-[10px] text-slate-400">(bạn)</span>` : ""}
          </div>
          <div class="flex items-center gap-1.5 mt-0.5">
            ${roleBadge(m.role)}
            ${m.is_online ? `<span class="text-[10px] text-emerald-600">● online</span>` : ""}
          </div>
        </div>
        ${
          canActOn
            ? `<button onclick="openMemberActions(${m.user_id})"
                 class="shrink-0 opacity-0 group-hover:opacity-100 w-6 h-6 flex items-center justify-center rounded hover:bg-slate-200 text-slate-500 transition">⋯</button>`
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
          <div class="font-bold text-slate-900 truncate">${escapeHtml(member.full_name)}</div>
          <div class="text-xs text-slate-500">@${escapeHtml(member.username)}</div>
        </div>
      </div>

      <div class="space-y-2">
        ${
          isOwner
            ? member.role === "ADMIN"
              ? `<button onclick="onChangeRole(${userId}, 'MEMBER')"
                   class="w-full text-left px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm hover:bg-slate-50">
                   ⬇️ Giáng xuống Thành viên
                 </button>`
              : `<button onclick="onChangeRole(${userId}, 'ADMIN')"
                   class="w-full text-left px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm hover:bg-slate-50">
                   ⬆️ Phong làm Quản trị viên
                 </button>`
            : ""
        }
        <button onclick="onRemoveMember(${userId})"
                class="w-full text-left px-3.5 py-2.5 border border-red-200 text-red-600 rounded-lg text-sm hover:bg-red-50">
          🚫 Xóa khỏi phòng
        </button>
        <button onclick="closeModal()"
                class="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50">
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
      <h3 class="font-bold text-lg text-slate-900 mb-1">Thêm thành viên</h3>
      <p class="text-xs text-slate-500 mb-4">Tìm theo tên, username hoặc email.</p>
      <input id="user-search-input" oninput="onSearchUsers(this.value)" autofocus
             class="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
             placeholder="Nhập để tìm..." />
      <div id="user-search-results" class="mt-3 space-y-1 max-h-64 overflow-y-auto scroll-thin"></div>
      <button onclick="closeModal()"
              class="w-full mt-4 py-2.5 border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50">Đóng</button>
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
        box.innerHTML = `<p class="text-xs text-slate-400 text-center py-3">Không tìm thấy ai phù hợp</p>`;
        return;
      }

      box.innerHTML = candidates
        .map(
          (u) => `<button onclick="onAddMember(${u.id})"
            class="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg hover:bg-slate-50 text-left">
            ${renderAvatar(u, 32)}
            <span class="min-w-0 flex-1">
              <span class="block text-xs font-medium text-slate-800 truncate">${escapeHtml(u.full_name)}</span>
              <span class="block text-[11px] text-slate-400 truncate">@${escapeHtml(u.username)}</span>
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

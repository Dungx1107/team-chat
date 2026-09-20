// ---------- Hồ sơ cá nhân ----------

function renderMyAvatarBar(user) {
  document.getElementById("my-avatar").innerHTML = renderAvatar(
    { ...user, is_online: true },
    34,
    { onDark: true }
  );
  document.getElementById("user-display-name").textContent = user.full_name;
  document.getElementById("user-display-status").textContent =
    user.status || `@${user.username}`;
}

async function openProfileModal() {
  let user;
  try {
    user = await api.getMyProfile();
    api.updateCurrentUser(user);
  } catch (err) {
    toast("Không tải được hồ sơ: " + err.message, "error");
    return;
  }

  openModal(`
    <div class="p-5">
      <h3 class="font-bold text-lg text-slate-900 mb-4">Hồ sơ của tôi</h3>

      <div class="flex items-center gap-4 mb-5">
        <div id="profile-avatar-preview">${renderAvatar(user, 64)}</div>
        <div class="min-w-0 flex-1">
          <button onclick="document.getElementById('avatar-input').click()"
                  class="px-3 py-1.5 text-xs font-medium border border-slate-200 rounded-lg hover:bg-slate-50 transition">
            Đổi ảnh đại diện
          </button>
          <p class="text-[10px] text-slate-400 mt-1.5">JPEG, PNG, GIF, WEBP · tối đa 5MB</p>
          <input type="file" id="avatar-input" accept="image/*" class="hidden" onchange="onAvatarSelected(event)" />
        </div>
      </div>

      <form onsubmit="onSaveProfile(event)" class="space-y-3.5">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1.5">Họ</label>
            <input id="profile-lastname" required maxlength="50" value="${escapeHtml(user.last_name)}"
                   class="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-600 mb-1.5">Tên</label>
            <input id="profile-firstname" required maxlength="50" value="${escapeHtml(user.first_name)}"
                   class="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
        </div>

        <div>
          <label class="block text-xs font-semibold text-slate-600 mb-1.5">Trạng thái</label>
          <input id="profile-status" maxlength="100" value="${escapeHtml(user.status || "")}"
                 class="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                 placeholder="ví dụ: Đang bận, Đang họp..." />
        </div>

        <div>
          <label class="block text-xs font-semibold text-slate-600 mb-1.5">Giới thiệu</label>
          <textarea id="profile-bio" maxlength="500" rows="3"
                    class="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500 resize-none scroll-thin"
                    placeholder="Đôi dòng về bạn...">${escapeHtml(user.bio || "")}</textarea>
        </div>

        <div class="text-[11px] text-slate-500 bg-slate-50 rounded-lg p-3 space-y-0.5">
          <div>Tên đăng nhập: <span class="font-mono text-slate-700">@${escapeHtml(user.username)}</span></div>
          <div>Email: <span class="font-mono text-slate-700">${escapeHtml(user.email)}</span></div>
          <div>Tham gia: ${new Date(user.created_at).toLocaleDateString("vi-VN")}</div>
        </div>

        <div class="flex gap-2 pt-1">
          <button type="button" onclick="closeModal()"
                  class="flex-1 py-2.5 border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50">Đóng</button>
          <button type="submit"
                  class="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold">Lưu thay đổi</button>
        </div>
      </form>
    </div>
  `);
}

async function onAvatarSelected(event) {
  const file = event.target.files[0];
  if (!file) return;

  if (file.size > 5 * 1024 * 1024) {
    toast("Ảnh vượt quá 5MB", "error");
    return;
  }

  const preview = document.getElementById("profile-avatar-preview");
  preview.innerHTML = `<div class="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center text-[10px] text-slate-400">Đang tải...</div>`;

  try {
    const user = await api.uploadAvatar(file);
    api.updateCurrentUser(user);
    // Thêm tham số thời gian để trình duyệt không dùng lại ảnh cũ trong cache
    preview.innerHTML = `<img src="${api.avatarUrl(user.id)}?t=${Date.now()}"
      class="w-16 h-16 rounded-full object-cover" alt="" />`;
    renderMyAvatarBar(user);
    toast("Đã cập nhật ảnh đại diện", "success");
    refreshVisibleAvatars();
  } catch (err) {
    toast("Tải ảnh thất bại: " + err.message, "error");
    preview.innerHTML = renderAvatar(api.getCurrentUser(), 64);
  }
}

async function onSaveProfile(event) {
  event.preventDefault();
  try {
    const user = await api.updateProfile({
      first_name: document.getElementById("profile-firstname").value.trim(),
      last_name: document.getElementById("profile-lastname").value.trim(),
      status: document.getElementById("profile-status").value.trim(),
      bio: document.getElementById("profile-bio").value.trim(),
    });
    api.updateCurrentUser(user);
    renderMyAvatarBar(user);
    closeModal();
    toast("Đã lưu hồ sơ", "success");
    refreshVisibleAvatars();
  } catch (err) {
    toast(err.message, "error");
  }
}

function refreshVisibleAvatars() {
  // Tên và ảnh hiển thị kèm tin nhắn nên nạp lại cho khớp
  if (currentRoom) {
    loadMessages().then(hydrateSecureMedia);
    loadMembers().then(() => membersPanelOpen && renderMembers());
  }
}

// ---------- Xem hồ sơ người khác ----------

async function openUserProfile(userId) {
  try {
    const user = await api.request(`/users/${userId}`);
    openModal(`
      <div class="p-5">
        <div class="flex items-center gap-4 mb-4">
          ${renderAvatar(user, 64)}
          <div class="min-w-0">
            <div class="font-bold text-lg text-slate-900 truncate">${escapeHtml(user.full_name)}</div>
            <div class="text-xs text-slate-500">@${escapeHtml(user.username)}</div>
            ${user.status ? `<div class="text-xs text-emerald-600 mt-1">${escapeHtml(user.status)}</div>` : ""}
          </div>
        </div>
        ${
          user.bio
            ? `<div class="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 leading-relaxed mb-4">${escapeHtml(user.bio)}</div>`
            : `<p class="text-xs text-slate-400 italic mb-4">Người này chưa viết giới thiệu.</p>`
        }
        <button onclick="closeModal()"
                class="w-full py-2.5 border border-slate-200 rounded-lg text-sm font-medium hover:bg-slate-50">Đóng</button>
      </div>
    `);
  } catch (err) {
    toast(err.message, "error");
  }
}

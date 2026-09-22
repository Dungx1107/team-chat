// ---------- Chống XSS ----------
// Mọi dữ liệu do người dùng nhập đều phải đi qua hàm này trước khi ghép vào HTML.
// Trước đây nội dung tin nhắn được chèn thẳng bằng innerHTML, nên chỉ cần gửi
// <img src=x onerror=alert(1)> là chạy được mã tùy ý trên máy người khác.
function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ---------- Định dạng ----------

function formatTime(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateLabel(iso) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  const sameDay = (a, b) => a.toDateString() === b.toDateString();
  if (sameDay(d, today)) return "Hôm nay";
  if (sameDay(d, yesterday)) return "Hôm qua";
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function syncThemeIcons() {
  const isDark = document.documentElement.classList.contains("dark");
  const icon = isDark ? "☀️" : "🌙";
  const authIcon = document.getElementById("theme-icon-auth");
  const chatIcon = document.getElementById("theme-icon-chat");
  if (authIcon) authIcon.textContent = icon;
  if (chatIcon) chatIcon.textContent = icon;
}

function toggleTheme() {
  const isDark = document.documentElement.classList.toggle("dark");
  localStorage.setItem("theme", isDark ? "dark" : "light");
  syncThemeIcons();
}

const colorScheme = window.matchMedia("(prefers-color-scheme: dark)");
colorScheme.addEventListener("change", (event) => {
  if (localStorage.getItem("theme") !== null) return;
  document.documentElement.classList.toggle("dark", event.matches);
  syncThemeIcons();
});

function toggleSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  if (!sidebar || !overlay) return;
  sidebar.classList.toggle("-translate-x-full");
  sidebar.classList.toggle("open");
  overlay.classList.toggle("hidden");
}

// ---------- Avatar ----------

// Màu nền suy ra từ id để mỗi người có một màu ổn định
const AVATAR_COLORS = [
  "bg-indigo-500", "bg-emerald-500", "bg-amber-500", "bg-rose-500",
  "bg-sky-500", "bg-violet-500", "bg-teal-500", "bg-orange-500",
];

function avatarColor(userId) {
  return AVATAR_COLORS[Math.abs(Number(userId) || 0) % AVATAR_COLORS.length];
}

function initialsOf(fullName, username) {
  const source = (fullName || username || "?").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Vẽ avatar. Nếu người dùng có ảnh thì hiện ảnh, không thì hiện chữ cái đầu.
 * onDark dùng cho viền chấm online trên nền tối của sidebar.
 */
function renderAvatar(user, size = 36, opts = {}) {
  const { hasAvatar, id, full_name, username, isOnline, onDark } = {
    hasAvatar: !!user.avatar_url,
    id: user.id ?? user.user_id,
    full_name: user.full_name,
    username: user.username,
    isOnline: user.is_online,
    onDark: false,
    ...opts,
  };

  const px = `${size}px`;
  const fontSize = size <= 28 ? "10px" : size <= 40 ? "12px" : "16px";
  const dot = isOnline
    ? `<span class="online-dot ${onDark ? "on-dark" : ""}"></span>`
    : "";

  // Luôn vẽ sẵn lớp chữ cái đầu ở dưới. Nếu có ảnh thì ảnh đè lên trên;
  // ảnh lỗi thì chỉ cần ẩn thẻ <img>, lớp dưới lộ ra -- không phải dựng lại DOM
  // bằng chuỗi HTML lồng nhau trong thuộc tính onerror.
  const imgLayer = hasAvatar
    ? `<img src="${escapeHtml(api.avatarUrl(id))}" alt=""
           style="width:${px};height:${px};position:absolute;inset:0"
           class="rounded-full object-cover"
           onerror="this.style.display='none'" />`
    : "";

  return `<span class="avatar-wrap" style="width:${px};height:${px}">
    ${renderInitialAvatar(id, full_name, username, size, fontSize)}
    ${imgLayer}
    ${dot}
  </span>`;
}

function renderInitialAvatar(id, fullName, username, size, fontSize) {
  return `<span style="width:${size}px;height:${size}px;font-size:${fontSize}"
    class="${avatarColor(id)} rounded-full flex items-center justify-center text-white font-bold shrink-0">
    ${escapeHtml(initialsOf(fullName, username))}
  </span>`;
}

// ---------- Nhãn vai trò ----------

const ROLE_LABELS = {
  OWNER: { text: "Chủ phòng", cls: "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300" },
  ADMIN: { text: "Quản trị", cls: "bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300" },
  MEMBER: { text: "Thành viên", cls: "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400" },
};

function roleBadge(role) {
  const r = ROLE_LABELS[role] || ROLE_LABELS.MEMBER;
  return `<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold ${r.cls}">${r.text}</span>`;
}

// ---------- Thông báo nổi ----------

function toast(message, type = "info") {
  const colors = {
    info: "bg-slate-800 dark:bg-slate-700 text-white",
    success: "bg-emerald-600 text-white",
    error: "bg-red-600 text-white",
  };
  const el = document.createElement("div");
  el.className = `toast px-4 py-2.5 rounded-lg shadow-lg text-sm max-w-xs ${colors[type] || colors.info}`;
  el.textContent = message;
  document.getElementById("toast-root").appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity .25s";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 250);
  }, 3000);
}

// ---------- Hộp thoại ----------

function openModal(html) {
  const root = document.getElementById("modal-root");
  root.innerHTML = `<div class="modal-backdrop" onclick="if(event.target===this) closeModal()">
    <div class="bg-white dark:bg-slate-900 dark:text-slate-100 rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto scroll-thin">
      ${html}
    </div>
  </div>`;
}

function closeModal() {
  document.getElementById("modal-root").innerHTML = "";
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

// ---------- Ô nhập tự giãn ----------

function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 128) + "px";
}

// ---------- Xem ảnh phóng to ----------

function openImageViewer(url) {
  const root = document.getElementById("modal-root");
  root.innerHTML = `<div class="modal-backdrop" onclick="closeModal()">
    <img src="${escapeHtml(url)}" class="max-w-[92vw] max-h-[92vh] rounded-lg shadow-2xl" alt="" />
  </div>`;
}

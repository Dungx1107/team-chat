// State quản lý phòng và polling
let currentRoom = null;
let pollTimer = null;

// --- Quản lý hiển thị Alert ---
function showAlert(msg, isSuccess = false) {
  const alertBox = document.getElementById("auth-alert");
  alertBox.classList.remove("hidden", "bg-red-50", "text-red-700", "border-red-200", "bg-emerald-50", "text-emerald-700", "border-emerald-200");
  
  if (isSuccess) {
    alertBox.classList.add("bg-emerald-50", "text-emerald-700", "border", "border-emerald-200");
  } else {
    alertBox.classList.add("bg-red-50", "text-red-700", "border", "border-red-200");
  }
  alertBox.innerText = msg;
}

function clearAlert() {
  const alertBox = document.getElementById("auth-alert");
  alertBox.classList.add("hidden");
  alertBox.innerText = "";
}

// --- Chuyển đổi qua lại giữa Tab Đăng nhập và Đăng ký ---
function switchAuthTab(tab) {
  clearAlert();
  const loginForm = document.getElementById("form-login");
  const regForm = document.getElementById("form-register");
  const loginBtn = document.getElementById("tab-login-btn");
  const regBtn = document.getElementById("tab-register-btn");

  if (tab === "login") {
    loginForm.classList.remove("hidden");
    regForm.classList.add("hidden");
    loginBtn.className = "flex-1 py-2 font-semibold text-indigo-600 border-b-2 border-indigo-600 text-sm";
    regBtn.className = "flex-1 py-2 font-semibold text-slate-500 text-sm";
  } else {
    loginForm.classList.add("hidden");
    regForm.classList.remove("hidden");
    regBtn.className = "flex-1 py-2 font-semibold text-indigo-600 border-b-2 border-indigo-600 text-sm";
    loginBtn.className = "flex-1 py-2 font-semibold text-slate-500 text-sm";
  }
}

// --- Xử lý Đăng Ký ---
async function onRegisterSubmit(event) {
  event.preventDefault();
  clearAlert();

  const payload = {
    first_name: document.getElementById("reg-firstname").value.trim(),
    last_name: document.getElementById("reg-lastname").value.trim(),
    username: document.getElementById("reg-username").value.trim(),
    email: document.getElementById("reg-email").value.trim(),
    password: document.getElementById("reg-password").value
  };

  try {
    await api.register(payload);
    showAlert("Đăng ký tài khoản thành công! Hãy chuyển sang Đăng nhập.", true);
    document.getElementById("form-register").reset();
    setTimeout(() => switchAuthTab("login"), 1200);
  } catch (err) {
    showAlert(err.message);
  }
}

// --- Xử lý Đăng Nhập ---
async function onLoginSubmit(event) {
  event.preventDefault();
  clearAlert();

  const credentials = {
    email: document.getElementById("login-email").value.trim(),
    password: document.getElementById("login-password").value
  };

  try {
    const data = await api.login(credentials);
    api.setSession(data.access_token, data.user);
    document.getElementById("form-login").reset();
    checkAuthState();
  } catch (err) {
    showAlert(err.message);
  }
}

// --- Xử lý Đăng Xuất ---
function handleLogout() {
  if (pollTimer) clearInterval(pollTimer);
  currentRoom = null;
  api.clearSession();
  checkAuthState();
}

// --- Quản lý Danh sách Phòng (Rooms) ---
async function loadRooms() {
  try {
    const rooms = await api.getRooms();
    const container = document.getElementById("room-list-container");
    container.innerHTML = "";

    if (!rooms || rooms.length === 0) {
      container.innerHTML = '<p class="text-xs text-slate-400 p-4 text-center">Chưa có phòng nào. Hãy tạo phòng mới!</p>';
      return;
    }

    rooms.forEach(r => {
      const isSelected = currentRoom && currentRoom.id === r.id;
      const div = document.createElement("div");
      div.className = `p-3 cursor-pointer hover:bg-slate-50 transition flex justify-between items-center ${
        isSelected ? "bg-indigo-50 border-r-4 border-indigo-600 font-semibold" : ""
      }`;
      div.onclick = () => selectRoom(r);
      div.innerHTML = `
        <div class="truncate">
          <div class="text-sm text-slate-800 truncate"># ${r.name}</div>
          <div class="text-[11px] text-slate-400">ID: ${r.id}</div>
        </div>
      `;
      container.appendChild(div);
    });
  } catch (err) {
    console.error("Lỗi tải phòng:", err);
  }
}

async function onPromptCreateRoom() {
  const name = prompt("Nhập tên phòng chat cần tạo:");
  if (!name || !name.trim()) return;

  try {
    const newRoom = await api.createRoom(name.trim());
    await loadRooms();
    selectRoom(newRoom);
  } catch (err) {
    alert("Không thể tạo phòng: " + err.message);
  }
}

function selectRoom(room) {
  currentRoom = room;
  const currentUser = api.getCurrentUser();

  // Cập nhật thông tin Header phòng
  document.getElementById("active-room-name").innerText = `# ${room.name}`;
  document.getElementById("active-room-desc").innerText = `Room ID: ${room.id} • Người tạo (Owner ID): ${room.owner_id}`;

  // Kiểm tra quyền: Chỉ chủ phòng mới hiện nút Xóa
  const delBtn = document.getElementById("btn-delete-room");
  if (currentUser && room.owner_id === currentUser.id) {
    delBtn.classList.remove("hidden");
  } else {
    delBtn.classList.add("hidden");
  }

  // Bật ô nhập và nút gửi tin
  document.getElementById("input-message").disabled = false;
  document.getElementById("btn-send-message").disabled = false;

  loadRooms();
  loadMessages();

  // Bật Polling tự động làm mới tin nhắn mỗi 2 giây
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(loadMessages, 2000);
}

async function loadMessages() {
  if (!currentRoom) return;

  try {
    const messages = await api.getMessages(currentRoom.id);
    const container = document.getElementById("messages-scroll-area");
    const currentUser = api.getCurrentUser();
    const currentUserId = currentUser ? Number(currentUser.id) : null;

    if (!messages || messages.length === 0) {
      container.innerHTML = '<p class="text-center text-slate-400 text-xs mt-12">Chưa có tin nhắn nào trong phòng này. Hãy gửi tin nhắn đầu tiên!</p>';
      return;
    }

    container.innerHTML = "";
    messages.forEach(m => {
      // So sánh ép kiểu an toàn
      const isMe = currentUserId !== null && Number(m.user_id) === currentUserId;
      const row = document.createElement("div");
      row.className = `flex flex-col ${isMe ? "items-end" : "items-start"}`;

      const timeStr = new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      
      // Hiển thị tên người gửi
      let senderText = "Tôi";
      if (!isMe) {
        if (m.sender_name && m.username) {
          senderText = `${m.sender_name} (@${m.username})`;
        } else {
          senderText = m.sender_name || (m.username ? `@${m.username}` : `User #${m.user_id}`);
        }
      }

      row.innerHTML = `
        <span class="text-[10px] text-slate-400 mb-1 px-1 font-medium">${senderText} • ${timeStr}</span>
        <div class="max-w-md px-4 py-2 rounded-2xl text-sm leading-relaxed shadow-sm ${
          isMe
            ? "bg-indigo-600 text-white rounded-br-none"
            : "bg-white border border-slate-200 text-slate-800 rounded-bl-none"
        }">
          ${m.content}
        </div>
      `;
      container.appendChild(row);
    });

    container.scrollTop = container.scrollHeight;
  } catch (err) {
    console.error("Lỗi nạp tin nhắn:", err);
  }
}

async function onSendMessageSubmit(event) {
  event.preventDefault();
  const input = document.getElementById("input-message");
  const content = input.value.trim();

  if (!content || !currentRoom) return;

  try {
    await api.sendMessage(currentRoom.id, content);
    input.value = "";
    loadMessages();
  } catch (err) {
    alert("Không gửi được tin nhắn: " + err.message);
  }
}

// --- Xóa Phòng Chat ---
async function onDeleteCurrentRoom() {
  if (!currentRoom) return;
  if (!confirm(`Bạn có chắc chắn muốn xóa vĩnh viễn phòng "${currentRoom.name}"?`)) return;

  try {
    await api.deleteRoom(currentRoom.id);
    if (pollTimer) clearInterval(pollTimer);
    currentRoom = null;

    // Reset giao diện về trạng thái chưa chọn
    document.getElementById("active-room-name").innerText = "Chưa chọn phòng nào";
    document.getElementById("active-room-desc").innerText = "Chọn một phòng ở danh sách bên trái để bắt đầu trò chuyện";
    document.getElementById("btn-delete-room").classList.add("hidden");
    document.getElementById("input-message").disabled = true;
    document.getElementById("btn-send-message").disabled = true;
    document.getElementById("messages-scroll-area").innerHTML = '<p class="text-center text-slate-400 text-xs mt-12">Phòng đã được xóa thành công.</p>';

    await loadRooms();
  } catch (err) {
    alert("Lỗi khi xóa phòng: " + err.message);
  }
}

// --- Khởi động Dashboard khi đã đăng nhập ---
window.initDashboard = function() {
  loadRooms();
};

// --- Kiểm tra trạng thái phiên làm việc ---
function checkAuthState() {
  const token = api.getToken();
  const user = api.getCurrentUser();
  const authView = document.getElementById("auth-view");
  const chatView = document.getElementById("chat-view");
  const userBar = document.getElementById("user-info-bar");
  const userNameDisplay = document.getElementById("user-display-name");

  if (token && user) {
    authView.classList.add("hidden");
    chatView.classList.remove("hidden");
    userBar.classList.remove("hidden");
    userNameDisplay.innerText = `${user.full_name} (@${user.username})`;
    window.initDashboard();
  } else {
    authView.classList.remove("hidden");
    chatView.classList.add("hidden");
    userBar.classList.add("hidden");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  checkAuthState();
});

// Trạng thái tin nhắn của phòng đang mở
let messagesCache = [];
let pendingFile = null;
let typingTimers = {};
let lastTypingSent = 0;

const EMOJI_CHOICES = ["👍", "❤️", "😂", "😮", "😢", "🎉"];

// ---------- Nạp và vẽ tin nhắn ----------

async function loadMessages() {
  if (!currentRoom) return;
  try {
    messagesCache = await api.getMessages(currentRoom.id);
    renderMessages();
  } catch (err) {
    const area = document.getElementById("messages-scroll-area");
    area.innerHTML = `<div class="text-center text-slate-400 dark:text-slate-500 text-xs mt-16">
      ${escapeHtml(err.message)}
    </div>`;
  }
}

function renderMessages(keepScroll = false) {
  const container = document.getElementById("messages-scroll-area");
  const wasAtBottom =
    container.scrollHeight - container.scrollTop - container.clientHeight < 80;

  if (!messagesCache.length) {
    container.innerHTML = `<div class="text-center text-slate-400 dark:text-slate-500 text-xs mt-16">
      Chưa có tin nhắn nào. Hãy gửi tin nhắn đầu tiên!
    </div>`;
    return;
  }

  const me = api.getCurrentUser();
  const myId = me ? Number(me.id) : null;
  let html = "";
  let lastDate = null;
  let lastSender = null;

  messagesCache.forEach((m) => {
    // Vạch ngăn theo ngày
    const dateLabel = formatDateLabel(m.created_at);
    if (dateLabel !== lastDate) {
      html += `<div class="flex items-center gap-3 py-3">
        <div class="flex-1 h-px bg-slate-200 dark:bg-slate-700"></div>
        <span class="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide">${escapeHtml(dateLabel)}</span>
        <div class="flex-1 h-px bg-slate-200 dark:bg-slate-700"></div>
      </div>`;
      lastDate = dateLabel;
      lastSender = null;
    }

    // Tin liên tiếp của cùng một người thì gộp, không lặp lại avatar
    const grouped = lastSender === m.user_id;
    html += renderMessageRow(m, myId, grouped);
    lastSender = m.user_id;
  });

  container.innerHTML = html;

  if (!keepScroll || wasAtBottom) {
    container.scrollTop = container.scrollHeight;
  }
}

function renderMessageRow(m, myId, grouped) {
  const isMe = myId !== null && Number(m.user_id) === myId;
  const senderName = m.sender_name || (m.username ? `@${m.username}` : `Người dùng #${m.user_id}`);
  const avatarHtml = grouped
    ? `<div class="w-9 shrink-0 text-[10px] text-slate-400 dark:text-slate-500 pt-1 opacity-0 group-hover:opacity-100"></div>`
    : `<div class="w-9 shrink-0 pt-0.5">${renderAvatar({
        id: m.user_id,
        avatar_url: m.avatar_url,
        full_name: m.sender_name,
        username: m.username,
      }, 36)}</div>`;

  const header = grouped
    ? ""
    : `<div class="flex items-baseline gap-2 mb-0.5 ${isMe ? "justify-end" : ""}">
        ${isMe ? "" : `<span class="font-semibold text-sm text-slate-900 dark:text-slate-100">${escapeHtml(senderName)}</span>`}
        ${isMe ? "" : m.username ? `<span class="text-[11px] text-slate-400 dark:text-slate-500">@${escapeHtml(m.username)}</span>` : ""}
        <span class="text-[10px] text-slate-400 dark:text-slate-500">${formatTime(m.created_at)}</span>
        ${m.edited_at ? `<span class="text-[10px] text-slate-400 dark:text-slate-500 italic">(đã sửa)</span>` : ""}
      </div>`;

  const bubble = m.is_deleted
    ? `<div class="text-xs text-slate-400 dark:text-slate-500 italic py-1">Tin nhắn đã bị xóa</div>`
    : `<div class="${isMe ? "bubble-me" : "bubble-other"} rounded-2xl ${isMe ? "rounded-br-sm" : "rounded-bl-sm"} px-3 py-1.5">
        ${renderMessageBody(m)}
      </div>`;
  const reactions = m.is_deleted ? "" : renderReactions(m, myId, isMe);
  const actions = m.is_deleted ? "" : renderMessageActions(m, isMe);
  const content = `<div class="msg-bubble-wrap relative flex flex-col ${isMe ? "items-end" : "items-start"}">
      ${header}
      ${bubble}
      ${reactions}
      ${actions}
    </div>`;

  return `<div class="msg-row group flex ${isMe ? "justify-end" : "justify-start"} gap-2 px-2 py-0.5 rounded-lg relative animate-in" data-msg-id="${m.id}">
    ${isMe ? content + avatarHtml : avatarHtml + content}
  </div>`;
}

function renderMessageBody(m) {
  let body = "";

  if (m.content) {
    body += `<div class="text-sm leading-relaxed whitespace-pre-wrap break-words">${escapeHtml(m.content)}</div>`;
  }

  if (m.attachment) {
    body += renderAttachment(m.attachment);
  }

  return body;
}

function renderAttachment(att) {
  const url = api.attachmentUrl(att.id);
  const safeName = escapeHtml(att.filename);
  const size = formatFileSize(att.size_bytes);

  if (att.kind === "IMAGE") {
    return `<div class="mt-1.5">
      <img data-secure-src="${escapeHtml(url)}" alt="${safeName}"
           class="msg-image rounded-lg max-w-full border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800"
           onclick="openImageViewer(this.src)" />
    </div>`;
  }

  if (att.kind === "VIDEO") {
    return `<div class="mt-1.5">
      <video data-secure-src="${escapeHtml(url)}" controls
             class="rounded-lg border border-slate-200 dark:border-slate-700 max-w-full bg-black"></video>
    </div>`;
  }

  if (att.kind === "AUDIO") {
    return `<div class="mt-1.5">
      <audio data-secure-src="${escapeHtml(url)}" controls class="max-w-full"></audio>
    </div>`;
  }

  return `<div class="mt-1.5">
    <button onclick="downloadAttachment(${att.id}, '${safeName.replace(/'/g, "\\'")}')"
            class="flex items-center gap-2.5 px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition text-left max-w-full w-full">
      <span class="text-xl shrink-0">📄</span>
      <span class="min-w-0">
        <span class="block text-xs font-medium text-slate-800 dark:text-slate-200 truncate">${safeName}</span>
        <span class="block text-[10px] text-slate-400 dark:text-slate-500">${size} · Bấm để tải về</span>
      </span>
    </button>
  </div>`;
}

function renderReactions(m, myId, isMe) {
  if (!m.reactions || !m.reactions.length) return "";
  const chips = m.reactions
    .map((r) => {
      const mine = myId !== null && r.user_ids.includes(myId);
      return `<button onclick="onToggleReaction(${m.id}, '${r.emoji}')"
        class="px-1.5 py-0.5 rounded-full text-[11px] border transition ${
          mine
            ? "bg-indigo-50 dark:bg-indigo-900/40 border-indigo-300 dark:border-indigo-700 text-indigo-700 dark:text-indigo-300"
            : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 text-slate-600 dark:text-slate-300"
        }">${r.emoji} ${r.count}</button>`;
    })
    .join("");
  // return `<div class="flex flex-wrap gap-1 mt-1 ${isMe ? "justify-end" : "justify-start"}">${chips}</div>`;
  // return `<div class="flex flex-wrap gap-1 -mt-1 justify-end">${chips}</div>`;
  return `<div class="flex flex-wrap gap-1 -mt-0.5 justify-end">${chips}</div>`;
}

function renderMessageActions(m, isMe) {
  const canDelete = isMe || (currentRoom && ["OWNER", "ADMIN"].includes(currentRoom.my_role));
  return `<div class="msg-actions absolute ${isMe ? "right-full mr-1" : "left-full ml-1"} top-0 z-20 flex items-center gap-0.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-sm px-1 py-0.5">
    ${EMOJI_CHOICES.map(
      (e) => `<button onclick="onToggleReaction(${m.id}, '${e}')"
        class="w-6 h-6 flex items-center justify-center rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-sm" title="Thả ${e}">${e}</button>`
    ).join("")}
    ${
      canDelete
        ? `<span class="w-px h-4 bg-slate-200 dark:bg-slate-700 mx-0.5"></span>
           <button onclick="onDeleteMessage(${m.id})" title="Xóa tin nhắn"
             class="w-6 h-6 flex items-center justify-center rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-red-500 text-xs">🗑</button>`
        : ""
    }
  </div>`;
}

// ---------- Tệp đính kèm cần token ----------
// Thẻ <img src> không gửi được header Authorization, nên phải tải bằng fetch
// rồi gán blob URL. Ảnh đại diện thì ngược lại: endpoint để công khai.

async function hydrateSecureMedia() {
  const nodes = document.querySelectorAll("[data-secure-src]");
  for (const node of nodes) {
    const url = node.getAttribute("data-secure-src");
    node.removeAttribute("data-secure-src");
    try {
      node.src = await api.fetchBlobUrl(url);
    } catch {
      node.replaceWith(
        document
          .createRange()
          .createContextualFragment(
            `<div class="text-xs text-slate-400 dark:text-slate-500 italic mt-1.5">Không tải được tệp đính kèm</div>`
          )
      );
    }
  }
}

async function downloadAttachment(attachmentId, filename) {
  try {
    const url = await api.fetchBlobUrl(api.attachmentUrl(attachmentId));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (err) {
    toast("Không tải được tệp: " + err.message, "error");
  }
}

// ---------- Gửi tin ----------

function onMessageKeyDown(event) {
  // Enter để gửi, Shift+Enter để xuống dòng
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    onSendMessageSubmit(event);
  }
}

async function onSendMessageSubmit(event) {
  event.preventDefault();
  if (!currentRoom) return;

  const input = document.getElementById("input-message");
  const content = input.value.trim();

  if (pendingFile) {
    await sendPendingFile(content);
    return;
  }

  if (!content) return;

  const sendBtn = document.getElementById("btn-send-message");
  sendBtn.disabled = true;
  try {
    await api.sendMessage(currentRoom.id, content);
    input.value = "";
    autoGrow(input);
    // Không tự nạp lại: sự kiện WebSocket sẽ đẩy tin nhắn về
    if (!realtime.isConnected()) await loadMessages();
  } catch (err) {
    toast("Không gửi được tin nhắn: " + err.message, "error");
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

function onFileSelected(event) {
  const file = event.target.files[0];
  if (!file) return;

  const MAX = 25 * 1024 * 1024;
  if (file.size > MAX) {
    toast("Tệp vượt quá 25MB", "error");
    event.target.value = "";
    return;
  }

  pendingFile = file;
  const preview = document.getElementById("upload-preview");
  preview.classList.remove("hidden");
  preview.innerHTML = `<div class="flex items-center gap-2.5 px-3 py-2 bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-800 rounded-lg">
    <span class="text-lg">${file.type.startsWith("image/") ? "🖼️" : "📄"}</span>
    <span class="min-w-0 flex-1">
      <span class="block text-xs font-medium text-slate-800 dark:text-slate-200 truncate">${escapeHtml(file.name)}</span>
      <span class="block text-[10px] text-slate-500 dark:text-slate-400">${formatFileSize(file.size)}</span>
    </span>
    <button type="button" onclick="clearPendingFile()"
            class="w-6 h-6 flex items-center justify-center rounded hover:bg-indigo-100 dark:hover:bg-indigo-900/40 text-slate-500">✕</button>
  </div>`;
  document.getElementById("input-message").focus();
}

function clearPendingFile() {
  pendingFile = null;
  document.getElementById("file-input").value = "";
  const preview = document.getElementById("upload-preview");
  preview.classList.add("hidden");
  preview.innerHTML = "";
}

async function sendPendingFile(caption) {
  const file = pendingFile;
  const preview = document.getElementById("upload-preview");
  preview.innerHTML = `<div class="px-3 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg text-xs text-slate-500 dark:text-slate-400">
    Đang tải lên ${escapeHtml(file.name)}...
  </div>`;

  try {
    await api.uploadFile(currentRoom.id, file, caption);
    document.getElementById("input-message").value = "";
    clearPendingFile();
    if (!realtime.isConnected()) await loadMessages();
  } catch (err) {
    toast("Tải tệp thất bại: " + err.message, "error");
    clearPendingFile();
  }
}

// ---------- Biểu cảm và xóa ----------

async function onToggleReaction(messageId, emoji) {
  try {
    const result = await api.toggleReaction(messageId, emoji);
    // Cập nhật ngay tại chỗ cho mượt, WebSocket sẽ đồng bộ lại sau
    applyReactionUpdate(result);
  } catch (err) {
    toast(err.message, "error");
  }
}

function applyReactionUpdate(payload) {
  const msg = messagesCache.find((m) => m.id === payload.message_id);
  if (!msg) return;
  msg.reactions = payload.reactions;
  renderMessages(true);
  hydrateSecureMedia();
}

async function onDeleteMessage(messageId) {
  if (!confirm("Xóa tin nhắn này?")) return;
  try {
    await api.deleteMessage(messageId);
    if (!realtime.isConnected()) await loadMessages();
  } catch (err) {
    toast("Không xóa được: " + err.message, "error");
  }
}

// ---------- Đang soạn tin ----------

function notifyTyping() {
  if (!currentRoom) return;
  const now = Date.now();
  // Chỉ báo tối đa 2 giây một lần để không spam server
  if (now - lastTypingSent < 2000) return;
  lastTypingSent = now;
  realtime.sendTyping(currentRoom.id);
}

function showTyping(userId) {
  const me = api.getCurrentUser();
  if (me && Number(userId) === Number(me.id)) return;

  const member = (membersCache || []).find((m) => m.user_id === userId);
  const name = member ? member.full_name : `Người dùng #${userId}`;

  typingTimers[userId] = { name, expires: Date.now() + 3000 };
  renderTypingIndicator();

  clearTimeout(typingTimers[userId].timer);
  typingTimers[userId].timer = setTimeout(() => {
    delete typingTimers[userId];
    renderTypingIndicator();
  }, 3000);
}

function renderTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  const names = Object.values(typingTimers).map((t) => t.name);
  if (!names.length) {
    el.textContent = "";
    return;
  }
  el.textContent =
    names.length === 1
      ? `${names[0]} đang soạn tin...`
      : `${names.length} người đang soạn tin...`;
}

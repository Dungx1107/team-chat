/**
 * Gọi thoại/video 1-1 bằng WebRTC.
 *
 * Luồng:
 *   Người gọi: xin quyền mic/cam -> POST /calls -> chờ call.accepted
 *              -> tạo RTCPeerConnection -> gửi offer qua WebSocket
 *   Người nghe: nhận call.incoming -> bấm nghe -> xin quyền mic/cam
 *              -> tạo RTCPeerConnection -> POST /calls/{id}/accept
 *              -> nhận offer, trả answer
 * Sau khi trao đổi offer/answer và ICE candidate, âm thanh/hình ảnh đi thẳng
 * giữa hai trình duyệt; server không nhận được luồng media nào.
 */
const callUI = {
  call: null,          // dữ liệu cuộc gọi từ server
  role: null,          // "caller" | "callee"
  peerId: null,        // id người bên kia
  pc: null,
  localStream: null,
  remoteStream: null,
  pendingSignals: [],  // tín hiệu đến trước khi RTCPeerConnection sẵn sàng
  pendingIce: [],      // ICE đến trước khi có remote description
  micOn: true,
  camOn: true,
  ringTimer: null,
  durationTimer: null,
  connectedAt: null,
  iceServers: null,
  ringTimeoutSeconds: 30,
  tone: null,

  // ---------- Tiện ích ----------

  isBusy() {
    return this.call !== null;
  },

  myId() {
    const me = api.getCurrentUser();
    return me ? Number(me.id) : null;
  },

  peerInfo() {
    if (!this.call) return null;
    return this.call.participants.find((p) => Number(p.id) === Number(this.peerId)) || null;
  },

  kindLabel(kind) {
    return kind === "AUDIO" ? "thoại" : "video";
  },

  async loadConfig() {
    if (this.iceServers) return;
    try {
      const cfg = await api.getCallConfig();
      this.iceServers = cfg.ice_servers || [];
      this.ringTimeoutSeconds = cfg.ring_timeout_seconds || 30;
    } catch {
      this.iceServers = [];
    }
  },

  mediaSupported() {
    // Trình duyệt chỉ cấp navigator.mediaDevices trên HTTPS hoặc localhost
    if (!window.isSecureContext || !navigator.mediaDevices || !window.RTCPeerConnection) {
      toast("Cần mở trang qua HTTPS (hoặc localhost) để dùng micro/camera", "error");
      return false;
    }
    return true;
  },

  async getMedia(kind) {
    const audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    if (kind === "VIDEO") {
      try {
        return await navigator.mediaDevices.getUserMedia({
          audio,
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
        });
      } catch (err) {
        // Không có camera hoặc bị chặn: vẫn cho gọi bằng tiếng
        toast("Không mở được camera, chuyển sang chỉ dùng micro", "error");
      }
    }
    try {
      return await navigator.mediaDevices.getUserMedia({ audio, video: false });
    } catch (err) {
      const reason = err && err.name === "NotAllowedError"
        ? "bạn đã chặn quyền truy cập micro"
        : "không tìm thấy micro";
      throw new Error(`Không gọi được: ${reason}`);
    }
  },

  // ---------- Người gọi ----------

  async startCall(userId, kind = "VIDEO") {
    if (this.isBusy()) {
      toast("Bạn đang trong một cuộc gọi khác", "error");
      return;
    }
    if (!currentRoom) return;
    if (!this.mediaSupported()) return;

    await this.loadConfig();

    try {
      this.localStream = await this.getMedia(kind);
    } catch (err) {
      toast(err.message, "error");
      return;
    }

    let call;
    try {
      call = await api.startCall(userId, currentRoom.id, kind);
    } catch (err) {
      this.stopLocalStream();
      toast(err.message, "error");
      return;
    }

    this.call = call;
    this.role = "caller";
    this.peerId = userId;
    this.resetControls();
    this.render("outgoing");
    this.playTone("ringback");

    // Không ai nghe máy thì tự dập và ghi nhận là cuộc gọi nhỡ
    this.ringTimer = setTimeout(() => this.hangup(true), this.ringTimeoutSeconds * 1000);
  },

  async onAccepted(call) {
    if (!this.call || call.id !== this.call.id) return;
    this.call = call;

    if (this.role === "callee") {
      // Tab này không phải tab vừa bấm nghe -> máy đã được nhận ở nơi khác
      if (!this.pc) {
        this.teardown();
        toast("Cuộc gọi đã được trả lời trên thiết bị khác");
      }
      return;
    }

    // Người gọi: bên kia đã nghe máy, bắt đầu dựng kết nối
    clearTimeout(this.ringTimer);
    this.stopTone();
    this.render("connecting");
    this.createPeerConnection();

    try {
      const offer = await this.pc.createOffer();
      await this.pc.setLocalDescription(offer);
      realtime.sendCallSignal(this.call.id, this.peerId, {
        type: "offer",
        sdp: this.pc.localDescription.sdp,
      });
    } catch (err) {
      console.error("Tạo offer lỗi:", err);
      this.hangup();
    }
  },

  // ---------- Người nghe ----------

  onIncoming(call) {
    const me = this.myId();
    if (this.isBusy()) return; // server đã chặn, đây chỉ là chốt an toàn phía client
    this.call = call;
    this.role = "callee";
    this.peerId = call.initiator_id;
    if (Number(this.peerId) === me) return;
    this.render("incoming");
    this.playTone("ring");
    this.notifyBrowser(call);
  },

  async accept() {
    if (!this.call || this.role !== "callee") return;
    this.stopTone();
    if (!this.mediaSupported()) {
      await this.decline();
      return;
    }

    await this.loadConfig();
    this.render("connecting");

    try {
      this.localStream = await this.getMedia(this.call.kind);
    } catch (err) {
      toast(err.message, "error");
      await this.decline();
      return;
    }

    // Dựng RTCPeerConnection TRƯỚC khi báo server đã nhận máy: server phát
    // call.accepted gần như tức thì, offer của người gọi có thể tới trước khi
    // request accept trả về.
    this.resetControls();
    this.createPeerConnection();

    try {
      const call = await api.acceptCall(this.call.id);
      this.call = call;
    } catch (err) {
      toast(err.message, "error");
      this.teardown();
      return;
    }

    // Xử lý các tín hiệu đã tới trong lúc chờ
    const queued = this.pendingSignals.splice(0);
    for (const s of queued) await this.handleSignal(s);
  },

  async decline() {
    if (!this.call) return;
    const id = this.call.id;
    this.teardown();
    try {
      await api.declineCall(id);
    } catch {
      // cuộc gọi có thể đã kết thúc ở phía bên kia
    }
  },

  // ---------- WebRTC ----------

  createPeerConnection() {
    this.pc = new RTCPeerConnection({ iceServers: this.iceServers || [] });

    this.localStream.getTracks().forEach((t) => this.pc.addTrack(t, this.localStream));

    this.pc.onicecandidate = (e) => {
      if (e.candidate && this.call) {
        realtime.sendCallSignal(this.call.id, this.peerId, {
          type: "ice",
          candidate: e.candidate.toJSON(),
        });
      }
    };

    this.pc.ontrack = (e) => {
      this.remoteStream = e.streams[0];
      const video = document.getElementById("call-remote-video");
      if (video && video.srcObject !== this.remoteStream) {
        video.srcObject = this.remoteStream;
        video.play().catch(() => {});
      }
      this.updateRemoteVisibility();
      e.track.onmute = () => this.updateRemoteVisibility();
      e.track.onunmute = () => this.updateRemoteVisibility();
    };

    this.pc.onconnectionstatechange = () => {
      const state = this.pc ? this.pc.connectionState : "closed";
      if (state === "connected") {
        if (!this.connectedAt) {
          this.connectedAt = Date.now();
          this.render("active");
          this.startDurationTimer();
        } else {
          this.setStatusText("");
        }
      } else if (state === "disconnected") {
        this.setStatusText("Mất kết nối, đang thử nối lại...");
      } else if (state === "failed") {
        toast("Không kết nối được tới người bên kia (mạng chặn kết nối trực tiếp)", "error");
        this.hangup();
      }
    };
  },

  async onSignal(data) {
    if (!this.call || data.call_id !== this.call.id) return;
    if (!this.pc) {
      // Tín hiệu tới sớm hơn lúc dựng xong kết nối -> giữ lại
      this.pendingSignals.push(data.signal);
      return;
    }
    await this.handleSignal(data.signal);
  },

  async handleSignal(signal) {
    try {
      if (signal.type === "offer") {
        await this.pc.setRemoteDescription({ type: "offer", sdp: signal.sdp });
        await this.flushIce();
        const answer = await this.pc.createAnswer();
        await this.pc.setLocalDescription(answer);
        realtime.sendCallSignal(this.call.id, this.peerId, {
          type: "answer",
          sdp: this.pc.localDescription.sdp,
        });
      } else if (signal.type === "answer") {
        await this.pc.setRemoteDescription({ type: "answer", sdp: signal.sdp });
        await this.flushIce();
      } else if (signal.type === "ice" && signal.candidate) {
        // ICE chỉ thêm được sau khi đã có remote description
        if (this.pc.remoteDescription) {
          await this.pc.addIceCandidate(signal.candidate);
        } else {
          this.pendingIce.push(signal.candidate);
        }
      }
    } catch (err) {
      console.error("Xử lý tín hiệu cuộc gọi lỗi:", err);
    }
  },

  async flushIce() {
    const list = this.pendingIce.splice(0);
    for (const c of list) {
      try {
        await this.pc.addIceCandidate(c);
      } catch (err) {
        console.warn("Bỏ qua ICE candidate lỗi:", err);
      }
    }
  },

  // ---------- Kết thúc ----------

  async hangup(missed = false) {
    if (!this.call) return;
    const id = this.call.id;
    this.teardown();
    try {
      await api.endCall(id, missed);
    } catch {
      // bên kia có thể đã dập máy trước
    }
    if (missed) toast("Không có người nghe máy");
  },

  onEnded(call) {
    if (!this.call || call.id !== this.call.id) return;
    const wasCaller = this.role === "caller";
    this.teardown();

    const duration = call.duration_seconds;
    const messages = {
      REJECTED: wasCaller ? "Người nhận đã từ chối cuộc gọi" : "Đã từ chối cuộc gọi",
      MISSED: wasCaller ? "Không có người nghe máy" : "Bạn có một cuộc gọi nhỡ",
      CANCELED: wasCaller ? "Đã hủy cuộc gọi" : "Người gọi đã hủy cuộc gọi",
      ENDED: `Cuộc gọi kết thúc${duration != null ? " · " + this.formatDuration(duration) : ""}`,
    };
    toast(messages[call.status] || "Cuộc gọi kết thúc");
  },

  teardown() {
    clearTimeout(this.ringTimer);
    clearInterval(this.durationTimer);
    this.ringTimer = null;
    this.durationTimer = null;
    this.stopTone();

    if (this.pc) {
      this.pc.ontrack = null;
      this.pc.onicecandidate = null;
      this.pc.onconnectionstatechange = null;
      try { this.pc.close(); } catch {}
    }
    this.stopLocalStream();

    this.pc = null;
    this.remoteStream = null;
    this.call = null;
    this.role = null;
    this.peerId = null;
    this.pendingSignals = [];
    this.pendingIce = [];
    this.connectedAt = null;

    document.getElementById("call-root").innerHTML = "";
  },

  stopLocalStream() {
    if (this.localStream) {
      this.localStream.getTracks().forEach((t) => t.stop());
      this.localStream = null;
    }
  },

  // ---------- Điều khiển trong cuộc gọi ----------

  resetControls() {
    this.micOn = true;
    this.camOn = true;
  },

  toggleMic() {
    if (!this.localStream) return;
    this.micOn = !this.micOn;
    this.localStream.getAudioTracks().forEach((t) => (t.enabled = this.micOn));
    this.renderControls();
  },

  toggleCam() {
    if (!this.localStream) return;
    const tracks = this.localStream.getVideoTracks();
    if (!tracks.length) {
      toast("Cuộc gọi này không có camera");
      return;
    }
    this.camOn = !this.camOn;
    tracks.forEach((t) => (t.enabled = this.camOn));
    this.renderControls();
    const local = document.getElementById("call-local-wrap");
    if (local) local.classList.toggle("hidden", !this.camOn);
  },

  // ---------- Âm báo (tự sinh bằng Web Audio, không cần tệp âm thanh) ----------

  playTone(type) {
    this.stopTone();
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const beep = () => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.frequency.value = type === "ring" ? 880 : 440;
        gain.gain.setValueAtTime(0.0001, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.9);
        osc.connect(gain).connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 1);
      };
      beep();
      const timer = setInterval(beep, type === "ring" ? 1500 : 3000);
      this.tone = { ctx, timer };
    } catch {
      this.tone = null;
    }
  },

  stopTone() {
    if (!this.tone) return;
    clearInterval(this.tone.timer);
    try { this.tone.ctx.close(); } catch {}
    this.tone = null;
  },

  notifyBrowser(call) {
    // Báo cả khi đang ở tab khác
    if (!document.hidden || !("Notification" in window)) return;
    const caller = call.participants.find((p) => p.id === call.initiator_id);
    const show = () => {
      try {
        new Notification("Cuộc gọi đến", {
          body: `${caller ? caller.full_name : "Ai đó"} đang gọi ${this.kindLabel(call.kind)} cho bạn`,
        });
      } catch {}
    };
    if (Notification.permission === "granted") show();
    else if (Notification.permission !== "denied") Notification.requestPermission().then((p) => p === "granted" && show());
  },

  // ---------- Đồng hồ ----------

  formatDuration(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  },

  startDurationTimer() {
    clearInterval(this.durationTimer);
    const tick = () => {
      if (!this.connectedAt) return;
      this.setStatusText(this.formatDuration(Math.floor((Date.now() - this.connectedAt) / 1000)));
    };
    tick();
    this.durationTimer = setInterval(tick, 1000);
  },

  setStatusText(text) {
    const el = document.getElementById("call-status");
    if (el) el.textContent = text;
  },

  // ---------- Giao diện ----------

  updateRemoteVisibility() {
    const video = document.getElementById("call-remote-video");
    const placeholder = document.getElementById("call-remote-placeholder");
    if (!video || !placeholder) return;
    const hasVideo =
      this.remoteStream &&
      this.remoteStream.getVideoTracks().some((t) => t.readyState === "live" && !t.muted);
    video.classList.toggle("invisible", !hasVideo);
    placeholder.classList.toggle("hidden", !!hasVideo);
  },

  controlButton(onclick, icon, label, active, danger = false) {
    const cls = danger
      ? "bg-red-600 hover:bg-red-700 text-white"
      : active
        ? "bg-white/15 hover:bg-white/25 text-white"
        : "bg-white text-slate-900 hover:bg-slate-200";
    return `<button onclick="${onclick}" title="${label}"
      class="w-14 h-14 rounded-full flex items-center justify-center text-xl transition shadow-lg ${cls}">${icon}</button>`;
  },

  renderControls() {
    const bar = document.getElementById("call-controls");
    if (!bar) return;
    const hasCam = this.localStream && this.localStream.getVideoTracks().length > 0;
    bar.innerHTML = `
      ${this.controlButton("callUI.toggleMic()", this.micOn ? "🎤" : "🔇", this.micOn ? "Tắt micro" : "Bật micro", this.micOn)}
      ${hasCam ? this.controlButton("callUI.toggleCam()", this.camOn ? "📹" : "🚫", this.camOn ? "Tắt camera" : "Bật camera", this.camOn) : ""}
      ${this.controlButton("callUI.hangup()", "✆", "Kết thúc", false, true)}
    `;
  },

  render(stage) {
    const root = document.getElementById("call-root");
    const peer = this.peerInfo() || { id: this.peerId, full_name: "Người dùng", username: "" };
    const name = escapeHtml(peer.full_name);
    const kind = this.kindLabel(this.call.kind);

    if (stage === "incoming") {
      root.innerHTML = `
        <div class="fixed inset-0 z-[45] flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm">
          <div class="w-full max-w-xs bg-white dark:bg-slate-900 rounded-3xl shadow-2xl p-6 text-center">
            <div class="flex justify-center mb-4">
              <div class="rounded-full ring-4 ring-emerald-400/60 animate-pulse">${renderAvatar(peer, 88)}</div>
            </div>
            <div class="font-bold text-lg text-slate-900 dark:text-slate-100 truncate">${name}</div>
            <div class="text-sm text-slate-500 dark:text-slate-400 mt-1">Cuộc gọi ${kind} đến...</div>
            <div class="flex justify-center gap-10 mt-7">
              <div class="flex flex-col items-center gap-1.5">
                <button onclick="callUI.decline()" title="Từ chối"
                  class="w-14 h-14 rounded-full bg-red-600 hover:bg-red-700 text-white text-xl shadow-lg transition">✕</button>
                <span class="text-[11px] text-slate-500">Từ chối</span>
              </div>
              <div class="flex flex-col items-center gap-1.5">
                <button onclick="callUI.accept()" title="Nghe máy"
                  class="w-14 h-14 rounded-full bg-emerald-500 hover:bg-emerald-600 text-white text-xl shadow-lg transition animate-bounce">✆</button>
                <span class="text-[11px] text-slate-500">Nghe</span>
              </div>
            </div>
          </div>
        </div>`;
      return;
    }

    // Màn hình cuộc gọi (đang gọi đi / đang kết nối / đang nói chuyện)
    const statusText = {
      outgoing: "Đang gọi...",
      connecting: "Đang kết nối...",
      active: "",
    }[stage];

    const existing = document.getElementById("call-stage");
    if (existing) {
      // Đã có khung cuộc gọi: chỉ cập nhật chữ, giữ nguyên thẻ video đang phát
      this.setStatusText(statusText);
      this.renderControls();
      return;
    }

    root.innerHTML = `
      <div id="call-stage" class="fixed inset-0 z-[45] bg-slate-950 text-white flex flex-col">
        <div class="absolute inset-0 flex items-center justify-center">
          <video id="call-remote-video" autoplay playsinline class="w-full h-full object-contain invisible"></video>
          <div id="call-remote-placeholder" class="absolute inset-0 flex flex-col items-center justify-center gap-4">
            ${renderAvatar(peer, 120)}
          </div>
        </div>

        <div class="relative z-10 pt-8 pb-4 text-center bg-gradient-to-b from-black/60 to-transparent">
          <div class="text-xl font-semibold truncate px-4">${name}</div>
          <div id="call-status" class="text-sm text-white/70 mt-1 h-5">${statusText}</div>
          <div class="text-[11px] text-white/40 mt-0.5">Cuộc gọi ${kind} · mã hóa đầu cuối (WebRTC)</div>
        </div>

        <div id="call-local-wrap" class="absolute right-4 bottom-28 z-10 w-32 sm:w-44 aspect-[3/4] sm:aspect-video rounded-xl overflow-hidden shadow-2xl ring-1 ring-white/20 bg-slate-800 ${
          this.localStream && this.localStream.getVideoTracks().length ? "" : "hidden"
        }">
          <video id="call-local-video" autoplay playsinline muted class="w-full h-full object-cover -scale-x-100"></video>
        </div>

        <div id="call-controls" class="relative z-10 mt-auto pb-8 pt-6 flex justify-center gap-5 bg-gradient-to-t from-black/60 to-transparent"></div>
      </div>`;

    const local = document.getElementById("call-local-video");
    if (local && this.localStream) local.srcObject = this.localStream;
    if (this.remoteStream) {
      const remote = document.getElementById("call-remote-video");
      remote.srcObject = this.remoteStream;
      this.updateRemoteVisibility();
    }
    this.renderControls();
  },
};

// Đăng ký sự kiện realtime cho cuộc gọi
realtime.on("call.incoming", (data) => callUI.onIncoming(data));
realtime.on("call.accepted", (data) => callUI.onAccepted(data));
realtime.on("call.ended", (data) => callUI.onEnded(data));
realtime.on("call.signal", (data) => callUI.onSignal(data));
realtime.on("call.error", (data) => {
  if (data && data.detail) console.warn("Lỗi tín hiệu cuộc gọi:", data.detail);
});

// Đóng tab giữa cuộc gọi: server sẽ tự kết thúc khi WebSocket ngắt,
// ở đây chỉ cần giải phóng camera/micro
window.addEventListener("pagehide", () => callUI.stopLocalStream());

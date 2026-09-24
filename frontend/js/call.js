/**
 * Gọi thoại/video bằng WebRTC: 1-1 và gọi nhóm trong phòng.
 *
 * Gọi 1-1: có đổ chuông, người nhận bấm nghe hoặc từ chối.
 * Gọi nhóm: không đổ chuông. Ai mở cuộc gọi thì cả phòng thấy thông báo và
 *           tự bấm tham gia.
 *
 * Gọi nhóm dùng mô hình mesh: mỗi người giữ một RTCPeerConnection riêng tới
 * từng người còn lại. N người thì mỗi máy có N-1 kết nối. Đơn giản và không
 * cần máy chủ media, nhưng chỉ chịu được nhóm nhỏ -- đông hơn phải dùng SFU.
 *
 * Quy ước tránh xung đột khi bắt tay: người đang ở trong cuộc gọi luôn là bên
 * gửi offer tới người mới vào. Người mới chỉ ngồi chờ và trả answer, nhờ vậy
 * không xảy ra cảnh hai bên cùng gửi offer cho nhau.
 */
const callUI = {
  call: null,          // dữ liệu cuộc gọi từ server
  role: null,          // "caller" | "callee" (chỉ dùng cho gọi 1-1)
  peers: new Map(),    // user_id -> { pc, stream, pendingSignals, pendingIce }
  localStream: null,
  micOn: true,
  camOn: true,
  ringTimer: null,
  durationTimer: null,
  connectedAt: null,
  iceServers: null,
  ringTimeoutSeconds: 30,
  maxGroupParticipants: 6,
  tone: null,
  roomCall: null,      // cuộc gọi nhóm đang diễn ra ở phòng đang mở

  // ---------- Tiện ích ----------

  isBusy() {
    return this.call !== null;
  },

  isGroup() {
    return !!this.call && this.call.mode === "GROUP";
  },

  myId() {
    const me = api.getCurrentUser();
    return me ? Number(me.id) : null;
  },

  participantInfo(userId) {
    if (!this.call) return null;
    return this.call.participants.find((p) => Number(p.id) === Number(userId)) || null;
  },

  /** Những người đang ở trong cuộc gọi, trừ mình. */
  otherActiveIds() {
    if (!this.call) return [];
    const me = this.myId();
    return (this.call.active_participant_ids || []).filter((id) => Number(id) !== me);
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
      this.maxGroupParticipants = cfg.max_group_participants || 6;
    } catch {
      this.iceServers = [];
    }
  },

  mediaSupported() {
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
      } catch {
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

  // ---------- Gọi 1-1: bên gọi ----------

  async startCall(userId, kind = "VIDEO") {
    if (this.isBusy()) {
      toast("Bạn đang trong một cuộc gọi khác", "error");
      return;
    }
    if (!currentRoom || !this.mediaSupported()) return;
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
    this.resetControls();
    this.render("outgoing");
    this.playTone("ringback");
    this.ringTimer = setTimeout(() => this.hangup(true), this.ringTimeoutSeconds * 1000);
  },

  async onAccepted(call) {
    if (!this.call || call.id !== this.call.id) return;
    this.call = call;

    if (this.role === "callee") {
      // Tab này không phải tab vừa bấm nghe -> máy đã được nhận ở nơi khác
      if (!this.peers.size) {
        this.teardown();
        toast("Cuộc gọi đã được trả lời trên thiết bị khác");
      }
      return;
    }

    clearTimeout(this.ringTimer);
    this.stopTone();
    this.render("connecting");
    // Bên gọi chủ động gửi offer
    const peerId = this.otherActiveIds()[0] ?? call.participants.find((p) => p.id !== this.myId())?.id;
    if (peerId) await this.ensurePeer(peerId, true);
  },

  // ---------- Gọi 1-1: bên nghe ----------

  onIncoming(call) {
    if (this.isBusy()) return;
    if (Number(call.initiator_id) === this.myId()) return;
    this.call = call;
    this.role = "callee";
    this.render("incoming");
    this.playTone("ring");
    this.notifyBrowser(call);
  },

  async accept() {
    if (!this.call || this.role !== "callee") return;
    this.stopTone();
    if (!this.mediaSupported()) return this.decline();

    await this.loadConfig();
    this.render("connecting");

    try {
      this.localStream = await this.getMedia(this.call.kind);
    } catch (err) {
      toast(err.message, "error");
      return this.decline();
    }

    this.resetControls();
    // Dựng sẵn kết nối tới người gọi TRƯỚC khi báo server đã nhận máy:
    // server phát call.accepted gần như tức thì, offer có thể tới trước khi
    // request accept trả về.
    const callerId = this.call.initiator_id;
    await this.ensurePeer(callerId, false);

    try {
      this.call = await api.acceptCall(this.call.id);
    } catch (err) {
      toast(err.message, "error");
      this.teardown();
    }
  },

  async decline() {
    if (!this.call) return;
    const id = this.call.id;
    this.teardown();
    try {
      await api.declineCall(id);
    } catch {}
  },

  // ---------- Gọi nhóm ----------

  async startGroupCall(kind = "VIDEO") {
    if (!currentRoom) return;
    if (this.isBusy()) {
      toast("Bạn đang trong một cuộc gọi khác", "error");
      return;
    }
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
      call = await api.startGroupCall(currentRoom.id, kind);
    } catch (err) {
      this.stopLocalStream();
      toast(err.message, "error");
      return;
    }

    this.call = call;
    this.role = "member";
    this.resetControls();
    this.connectedAt = Date.now();
    this.render("group");
    this.startDurationTimer();

    // Vào một cuộc gọi đã có sẵn: những người trong đó sẽ gửi offer tới mình,
    // nên ở đây chỉ cần chờ.
    this.updateRoomCallBanner(null);
  },

  /** Tham gia cuộc gọi nhóm đang diễn ra trong phòng. */
  async joinRoomCall() {
    const target = this.roomCall;
    if (!target) return;
    await this.startGroupCall(target.kind);
  },

  async leaveCall() {
    if (!this.call) return;
    const id = this.call.id;
    this.teardown();
    try {
      await api.leaveCall(id);
    } catch {}
  },

  async onParticipantJoined(data) {
    if (!this.call || data.call_id !== this.call.id) return;
    this.call = data.call || this.call;
    const newcomer = Number(data.user.id);
    if (newcomer === this.myId()) return;

    toast(`${data.user.full_name} đã tham gia cuộc gọi`);
    // Mình đã ở trong cuộc gọi -> mình là bên gửi offer cho người mới
    await this.ensurePeer(newcomer, true);
    this.render("group");
  },

  onParticipantLeft(data) {
    if (!this.call || data.call_id !== this.call.id) return;
    this.call = data.call || this.call;
    const gone = Number(data.user_id);
    this.closePeer(gone);

    const info = this.participantInfo(gone);
    if (info) toast(`${info.full_name} đã rời cuộc gọi`);

    if (this.call.status !== "ACTIVE") {
      this.teardown();
      return;
    }
    this.render("group");
  },

  // ---------- Banner cuộc gọi nhóm của phòng ----------

  async refreshRoomCall() {
    if (!currentRoom) {
      this.updateRoomCallBanner(null);
      return;
    }
    try {
      const call = await api.getRoomActiveCall(currentRoom.id);
      this.updateRoomCallBanner(call);
    } catch {
      this.updateRoomCallBanner(null);
    }
  },

  onRoomCallEvent(call, ended = false) {
    if (!currentRoom || !call || call.room_id !== currentRoom.id) return;
    this.updateRoomCallBanner(ended ? null : call);
  },

  updateRoomCallBanner(call) {
    this.roomCall = call && call.status === "ACTIVE" ? call : null;
    const el = document.getElementById("room-call-banner");
    if (!el) return;

    // Đang ở trong chính cuộc gọi đó thì không cần mời tham gia nữa
    const inThisCall = this.call && this.roomCall && this.call.id === this.roomCall.id;
    if (!this.roomCall || inThisCall) {
      el.classList.add("hidden");
      el.innerHTML = "";
      return;
    }

    const n = (this.roomCall.active_participant_ids || []).length;
    const names = (this.roomCall.participants || [])
      .filter((p) => (this.roomCall.active_participant_ids || []).includes(p.id))
      .map((p) => p.full_name);

    el.classList.remove("hidden");
    el.innerHTML = `
      <div class="flex items-center gap-3 px-4 py-2.5 bg-emerald-50 dark:bg-emerald-900/30 border-b border-emerald-200 dark:border-emerald-800">
        <span class="relative flex h-2.5 w-2.5 shrink-0">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
        </span>
        <div class="min-w-0 flex-1">
          <div class="text-xs font-semibold text-emerald-800 dark:text-emerald-200">
            Cuộc gọi ${this.kindLabel(this.roomCall.kind)} nhóm đang diễn ra · ${n} người
          </div>
          <div class="text-[11px] text-emerald-700/70 dark:text-emerald-300/70 truncate">${escapeHtml(names.join(", "))}</div>
        </div>
        <button onclick="callUI.joinRoomCall()"
          class="shrink-0 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg transition">
          Tham gia
        </button>
      </div>`;
  },

  // ---------- WebRTC nhiều kết nối ----------

  async ensurePeer(userId, createOffer) {
    userId = Number(userId);
    if (this.peers.has(userId)) return this.peers.get(userId);

    const pc = new RTCPeerConnection({ iceServers: this.iceServers || [] });
    const peer = { pc, stream: null, pendingSignals: [], pendingIce: [] };
    this.peers.set(userId, peer);

    if (this.localStream) {
      this.localStream.getTracks().forEach((t) => pc.addTrack(t, this.localStream));
    }

    pc.onicecandidate = (e) => {
      if (e.candidate && this.call) {
        realtime.sendCallSignal(this.call.id, userId, {
          type: "ice",
          candidate: e.candidate.toJSON(),
        });
      }
    };

    pc.ontrack = (e) => {
      peer.stream = e.streams[0];
      this.attachRemoteStream(userId, peer.stream);
      e.track.onmute = () => this.updateTileVisibility(userId);
      e.track.onunmute = () => this.updateTileVisibility(userId);
    };

    pc.onconnectionstatechange = () => {
      const state = pc.connectionState;
      if (state === "connected") {
        if (!this.connectedAt) {
          this.connectedAt = Date.now();
          this.render(this.isGroup() ? "group" : "active");
          this.startDurationTimer();
        }
        this.updateTileVisibility(userId);
      } else if (state === "failed") {
        if (this.isGroup()) {
          // Nhóm: hỏng một kết nối thì bỏ người đó, cuộc gọi vẫn tiếp tục
          const info = this.participantInfo(userId);
          toast(`Mất kết nối với ${info ? info.full_name : "một người"}`, "error");
          this.closePeer(userId);
          this.render("group");
        } else {
          toast("Không kết nối được tới người bên kia (mạng chặn kết nối trực tiếp)", "error");
          this.hangup();
        }
      }
    };

    // Xử lý các tín hiệu đã tới trước khi kết nối kịp dựng xong
    const queued = peer.pendingSignals.splice(0);
    for (const s of queued) await this.handleSignal(userId, s);

    if (createOffer) {
      try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        realtime.sendCallSignal(this.call.id, userId, {
          type: "offer",
          sdp: pc.localDescription.sdp,
        });
      } catch (err) {
        console.error("Tạo offer lỗi:", err);
      }
    }
    return peer;
  },

  closePeer(userId) {
    userId = Number(userId);
    const peer = this.peers.get(userId);
    if (!peer) return;
    peer.pc.ontrack = null;
    peer.pc.onicecandidate = null;
    peer.pc.onconnectionstatechange = null;
    try { peer.pc.close(); } catch {}
    this.peers.delete(userId);
    const tile = document.getElementById(`call-tile-${userId}`);
    if (tile) tile.remove();
  },

  async onSignal(data) {
    if (!this.call || data.call_id !== this.call.id) return;
    const from = Number(data.from_user_id);

    let peer = this.peers.get(from);
    if (!peer) {
      // Người mới gửi offer tới mà mình chưa dựng kết nối -> dựng và chờ offer
      if (data.signal.type === "offer") {
        peer = await this.ensurePeer(from, false);
      } else {
        return;
      }
    }
    await this.handleSignal(from, data.signal);
  },

  async handleSignal(userId, signal) {
    const peer = this.peers.get(Number(userId));
    if (!peer) return;
    const pc = peer.pc;

    try {
      if (signal.type === "offer") {
        await pc.setRemoteDescription({ type: "offer", sdp: signal.sdp });
        await this.flushIce(peer);
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        realtime.sendCallSignal(this.call.id, userId, {
          type: "answer",
          sdp: pc.localDescription.sdp,
        });
      } else if (signal.type === "answer") {
        await pc.setRemoteDescription({ type: "answer", sdp: signal.sdp });
        await this.flushIce(peer);
      } else if (signal.type === "ice" && signal.candidate) {
        if (pc.remoteDescription) {
          await pc.addIceCandidate(signal.candidate);
        } else {
          peer.pendingIce.push(signal.candidate);
        }
      }
    } catch (err) {
      console.error("Xử lý tín hiệu cuộc gọi lỗi:", err);
    }
  },

  async flushIce(peer) {
    const list = peer.pendingIce.splice(0);
    for (const c of list) {
      try {
        await peer.pc.addIceCandidate(c);
      } catch (err) {
        console.warn("Bỏ qua ICE candidate lỗi:", err);
      }
    }
  },

  // ---------- Kết thúc ----------

  async hangup(missed = false) {
    if (!this.call) return;
    if (this.isGroup()) return this.leaveCall();

    const id = this.call.id;
    this.teardown();
    try {
      await api.endCall(id, missed);
    } catch {}
    if (missed) toast("Không có người nghe máy");
  },

  onEnded(call) {
    if (!this.call || call.id !== this.call.id) return;
    const wasCaller = this.role === "caller";
    const wasGroup = this.isGroup();
    this.teardown();

    if (wasGroup) {
      toast("Cuộc gọi nhóm đã kết thúc");
      return;
    }

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

    for (const userId of Array.from(this.peers.keys())) this.closePeer(userId);
    this.stopLocalStream();

    this.call = null;
    this.role = null;
    this.connectedAt = null;
    document.getElementById("call-root").innerHTML = "";
    this.refreshRoomCall();
  },

  stopLocalStream() {
    if (this.localStream) {
      this.localStream.getTracks().forEach((t) => t.stop());
      this.localStream = null;
    }
  },

  // ---------- Điều khiển ----------

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
    this.updateTileVisibility(this.myId());
  },

  // ---------- Âm báo ----------

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
      this.tone = { ctx, timer: setInterval(beep, type === "ring" ? 1500 : 3000) };
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

  attachRemoteStream(userId, stream) {
    const video = document.getElementById(`call-video-${userId}`);
    if (video && video.srcObject !== stream) {
      video.srcObject = stream;
      video.play().catch(() => {});
    }
    this.updateTileVisibility(userId);
  },

  updateTileVisibility(userId) {
    const video = document.getElementById(`call-video-${userId}`);
    const holder = document.getElementById(`call-placeholder-${userId}`);
    if (!video || !holder) return;

    let hasVideo;
    if (Number(userId) === this.myId()) {
      hasVideo = this.localStream && this.localStream.getVideoTracks().some((t) => t.enabled);
    } else {
      const peer = this.peers.get(Number(userId));
      hasVideo = peer && peer.stream &&
        peer.stream.getVideoTracks().some((t) => t.readyState === "live" && !t.muted);
    }
    video.classList.toggle("invisible", !hasVideo);
    holder.classList.toggle("hidden", !!hasVideo);
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
    const leaveLabel = this.isGroup() ? "Rời cuộc gọi" : "Kết thúc";
    bar.innerHTML = `
      ${this.controlButton("callUI.toggleMic()", this.micOn ? "🎤" : "🔇", this.micOn ? "Tắt micro" : "Bật micro", this.micOn)}
      ${hasCam ? this.controlButton("callUI.toggleCam()", this.camOn ? "📹" : "🚫", this.camOn ? "Tắt camera" : "Bật camera", this.camOn) : ""}
      ${this.controlButton("callUI.hangup()", "✆", leaveLabel, false, true)}
    `;
  },

  /** Ô video của một người trong lưới. */
  tile(user, isMe = false) {
    const id = user.id;
    return `<div id="call-tile-${id}" class="relative bg-slate-800 rounded-xl overflow-hidden ring-1 ring-white/10 aspect-video">
      <video id="call-video-${id}" autoplay playsinline ${isMe ? "muted" : ""}
        class="w-full h-full object-cover invisible ${isMe ? "-scale-x-100" : ""}"></video>
      <div id="call-placeholder-${id}" class="absolute inset-0 flex items-center justify-center">
        ${renderAvatar(user, 64)}
      </div>
      <div class="absolute bottom-1.5 left-2 right-2 text-[11px] text-white/90 truncate drop-shadow">
        ${escapeHtml(user.full_name)}${isMe ? " (bạn)" : ""}
      </div>
    </div>`;
  },

  render(stage) {
    const root = document.getElementById("call-root");
    if (!this.call) return;

    // --- Cuộc gọi 1-1 đang đổ chuông ---
    if (stage === "incoming") {
      const peer = this.participantInfo(this.call.initiator_id) || { id: this.call.initiator_id, full_name: "Người dùng" };
      root.innerHTML = `
        <div class="fixed inset-0 z-[45] flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm">
          <div class="w-full max-w-xs bg-white dark:bg-slate-900 rounded-3xl shadow-2xl p-6 text-center">
            <div class="flex justify-center mb-4">
              <div class="rounded-full ring-4 ring-emerald-400/60 animate-pulse">${renderAvatar(peer, 88)}</div>
            </div>
            <div class="font-bold text-lg text-slate-900 dark:text-slate-100 truncate">${escapeHtml(peer.full_name)}</div>
            <div class="text-sm text-slate-500 dark:text-slate-400 mt-1">Cuộc gọi ${this.kindLabel(this.call.kind)} đến...</div>
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

    const statusText = { outgoing: "Đang gọi...", connecting: "Đang kết nối..." }[stage] || "";
    const title = this.isGroup()
      ? `${currentRoom ? "# " + currentRoom.name : "Cuộc gọi nhóm"}`
      : escapeHtml((this.participantInfo(this.otherActiveIds()[0]) ||
          this.call.participants.find((p) => p.id !== this.myId()) || { full_name: "Người dùng" }).full_name);

    const me = api.getCurrentUser() || {};
    const meTile = { id: this.myId(), full_name: me.full_name || "Tôi", avatar_url: me.avatar_url, username: me.username };
    const others = this.otherActiveIds().map(
      (id) => this.participantInfo(id) || { id, full_name: `Người dùng #${id}` }
    );

    const waiting = this.isGroup() && others.length === 0
      ? `<div class="absolute inset-x-0 bottom-28 text-center text-sm text-white/60">Đang chờ người khác tham gia...</div>`
      : "";

    const existing = document.getElementById("call-stage");
    if (existing) {
      // Đã có khung: chỉ vẽ lại lưới, giữ nguyên các thẻ video đang phát
      this.renderGrid(meTile, others);
      this.setStatusText(statusText || this.statusFallback());
      this.renderControls();
      const w = document.getElementById("call-waiting");
      if (w) w.innerHTML = waiting;
      return;
    }

    root.innerHTML = `
      <div id="call-stage" class="fixed inset-0 z-[45] bg-slate-950 text-white flex flex-col">
        <div class="pt-6 pb-3 text-center shrink-0">
          <div class="text-lg font-semibold truncate px-4">${title}</div>
          <div id="call-status" class="text-sm text-white/70 mt-1 h-5">${statusText}</div>
          <div class="text-[11px] text-white/40 mt-0.5">
            Cuộc gọi ${this.kindLabel(this.call.kind)}${this.isGroup() ? " nhóm" : ""} · truyền thẳng giữa các máy (WebRTC)
          </div>
        </div>

        <div id="call-grid" class="flex-1 min-h-0 px-4 pb-2 overflow-y-auto scroll-thin"></div>
        <div id="call-waiting" class="relative">${waiting}</div>

        <div id="call-controls" class="shrink-0 pb-8 pt-4 flex justify-center gap-5"></div>
      </div>`;

    this.renderGrid(meTile, others);
    this.renderControls();
  },

  statusFallback() {
    return this.connectedAt
      ? this.formatDuration(Math.floor((Date.now() - this.connectedAt) / 1000))
      : "";
  },

  renderGrid(meTile, others) {
    const grid = document.getElementById("call-grid");
    if (!grid) return;

    const total = others.length + 1;
    const cols = total <= 1 ? 1 : total <= 4 ? 2 : 3;
    grid.className = `flex-1 min-h-0 px-4 pb-2 overflow-y-auto scroll-thin grid gap-3 content-center`;
    grid.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;

    const wanted = [meTile, ...others];
    const wantedIds = wanted.map((u) => String(u.id));

    // Bỏ ô của người đã rời
    Array.from(grid.children).forEach((child) => {
      const id = child.id.replace("call-tile-", "");
      if (!wantedIds.includes(id)) child.remove();
    });

    // Thêm ô còn thiếu, không đụng vào ô đã có để video không bị ngắt
    wanted.forEach((u) => {
      if (!document.getElementById(`call-tile-${u.id}`)) {
        grid.insertAdjacentHTML("beforeend", this.tile(u, Number(u.id) === this.myId()));
        if (Number(u.id) === this.myId()) {
          const v = document.getElementById(`call-video-${u.id}`);
          if (v && this.localStream) v.srcObject = this.localStream;
        } else {
          const peer = this.peers.get(Number(u.id));
          if (peer && peer.stream) this.attachRemoteStream(u.id, peer.stream);
        }
        this.updateTileVisibility(u.id);
      }
    });
  },
};

// ---------- Sự kiện realtime ----------

realtime.on("call.incoming", (d) => callUI.onIncoming(d));
realtime.on("call.accepted", (d) => callUI.onAccepted(d));
realtime.on("call.ended", (d) => callUI.onEnded(d));
realtime.on("call.signal", (d) => callUI.onSignal(d));
realtime.on("call.participant_joined", (d) => callUI.onParticipantJoined(d));
realtime.on("call.participant_left", (d) => callUI.onParticipantLeft(d));
realtime.on("call.room_started", (d) => callUI.onRoomCallEvent(d));
realtime.on("call.room_updated", (d) => callUI.onRoomCallEvent(d));
realtime.on("call.room_ended", (d) => callUI.onRoomCallEvent(d, true));
realtime.on("call.error", (d) => {
  if (d && d.detail) console.warn("Lỗi tín hiệu cuộc gọi:", d.detail);
});

// Đóng tab giữa cuộc gọi: server tự dọn khi WebSocket ngắt,
// ở đây chỉ cần giải phóng camera/micro
window.addEventListener("pagehide", () => callUI.stopLocalStream());

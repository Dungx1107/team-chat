/**
 * ============================================================================
 * call.js — Hệ thống gọi thoại/video WebRTC (1-1 và gọi nhóm).
 * ============================================================================
 *
 * TỔNG QUAN
 * ---------
 * Module này quản lý toàn bộ vòng đời cuộc gọi phía client:
 *   - Khởi tạo / nhận / chấp nhận / từ chối / kết thúc cuộc gọi.
 *   - Thiết lập các kết nối peer-to-peer qua WebRTC (RTCPeerConnection).
 *   - Trao đổi SDP offer/answer và ICE candidate qua WebSocket (realtime).
 *   - Render giao diện cuộc gọi (lưới video, nút điều khiển, banner phòng).
 *
 * HAI CHẾ ĐỘ GỌI
 * ---------------
 * 1) Gọi 1-1 (DIRECT):
 *    - Có đổ chuông. Người nhận bấm "Nghe" hoặc "Từ chối".
 *
 * 2) Gọi nhóm (GROUP):
 *    - KHÔNG đổ chuông. Ai mở cuộc gọi thì cả phòng thấy banner và tự bấm
 *      "Tham gia" — giống mô hình phòng họp (Zoom/Meet) hơn là gọi điện.
 *
 * MÔ HÌNH MESH CHO GỌI NHÓM
 * -------------------------
 * Mỗi client giữ N-1 RTCPeerConnection — một kết nối riêng tới TỪNG người
 * còn lại. Ưu: không cần máy chủ media (SFU/MCU). Nhược: băng thông upload
 * tăng theo N, chỉ chịu được nhóm nhỏ (~6 người). Đông hơn phải dùng SFU.
 *
 * QUY ƯỚC CHỐNG XUNG ĐỘT OFFER (GLARE)
 * ------------------------------------
 * Nếu cả hai bên cùng gửi offer → xung đột (glare) → kết nối thất bại.
 * Quy ước ở đây:
 *   - Người ĐÃ Ở TRONG cuộc gọi  → chủ động gửi offer.
 *   - Người MỚI VÀO              → chỉ chờ và trả answer.
 * Nhờ vậy không bao giờ có hai offer chéo nhau.
 */

/**
 * CHẾ ĐỘ THỬ TURN — bật bằng query string `?relay=1`.
 *
 * Khi bật, mọi RTCPeerConnection bị ép dùng `iceTransportPolicy: "relay"`,
 * nghĩa là KHÔNG cho phép kết nối trực tiếp (host/srflx), buộc media phải
 * vòng qua máy chủ TURN.
 *
 * MỤC ĐÍCH
 * --------
 * 1) Kiểm chứng TURN hoạt động mà không cần dựng 2 mạng khác nhau (NAT khác).
 * 2) Demo trực quan hai đường đi: direct vs relay.
 * 3) Có thể coi là "chế độ riêng tư": qua TURN, đối phương không thấy IP thật.
 *
 * LƯU Ý HIỆU NĂNG
 * ---------------
 * Mặc định TẮT vì ép relay làm TỐN BĂNG THÔNG TURN và TĂNG ĐỘ TRỄ, kể cả khi
 * hai máy ngồi cạnh nhau. Đặt trong query string (không lưu localStorage) để
 * tải lại trang không có tham số là tự trở về bình thường — tránh vô tình
 * bật mãi.
 */
const FORCE_RELAY =
  new URLSearchParams(window.location.search).get("relay") === "1";

/**
 * callUI — singleton quản lý toàn bộ trạng thái và hành vi cuộc gọi.
 *
 * Mọi thao tác UI (nút bấm, render) và mọi sự kiện realtime đều đi qua object
 * này. Việc giữ toàn bộ state trong MỘT object giúp dễ debug, dễ teardown
 * (chỉ cần reset các field), và tránh rò rỉ closure.
 */
const callUI = {
  // ===========================================================================
  // STATE — Trạng thái runtime của cuộc gọi
  // ===========================================================================

  /** Dữ liệu cuộc gọi hiện tại từ server. `null` = không có cuộc gọi nào. */
  call: null,

  /** "caller" | "callee" | "member" — phân biệt luồng gọi 1-1. */
  role: null,

  /**
   * Map<userId, { pc, stream, pendingSignals, pendingIce }>.
   * Mỗi entry = một kết nối WebRTC tới một người khác.
   *   - pc:              RTCPeerConnection
   *   - stream:          MediaStream nhận được từ ontrack
   *   - pendingSignals:  tín hiệu đến TRƯỚC khi peer được tạo xong
   *   - pendingIce:      ICE candidate đến TRƯỚC khi có remoteDescription
   */
  peers: new Map(),

  /** MediaStream cục bộ (mic + camera của chính mình). */
  localStream: null,

  /** Trạng thái mic/cam cục bộ — dùng để render icon và broadcast cho peer. */
  micOn: true,
  camOn: true,

  /** Timer đổ chuông (gọi 1-1). Hết hạn → tự hủy cuộc gọi. */
  ringTimer: null,

  /** Timer cập nhật đồng hồ đếm thời lượng cuộc gọi mỗi giây. */
  durationTimer: null,

  /** Timestamp (ms) lúc kết nối WebRTC đầu tiên thành công. */
  connectedAt: null,

  /** Cấu hình ICE servers (STUN/TURN) tải từ server. `null` = chưa tải. */
  iceServers: null,

  /** Thời gian đổ chuông tối đa (giây) — server cấu hình được. */
  ringTimeoutSeconds: 30,

  /** Số người tối đa trong cuộc gọi nhóm — server cấu hình được. */
  maxGroupParticipants: 6,

  /** Âm thanh đổ chuông/ringback đang phát (Web Audio API). */
  tone: null,

  /** Cuộc gọi nhóm đang diễn ra trong phòng hiện tại (để hiện banner). */
  roomCall: null,

  /** Map<userId, "direct"|"relay"> — đường đi thực tế của media. */
  paths: new Map(),

  /** Map<userId, { camera, mic }> — trạng thái thiết bị của người kia. */
  peerMedia: new Map(),

  // ===========================================================================
  // TIỆN ÍCH — Utility methods
  // ===========================================================================

  /** Đang có cuộc gọi hay không (bất kể 1-1 hay nhóm). */
  isBusy() {
    return this.call !== null;
  },

  /** Cuộc gọi hiện tại có phải nhóm không. */
  isGroup() {
    return !!this.call && this.call.mode === "GROUP";
  },

  /** ID người dùng hiện tại (đã ép kiểu Number để so sánh an toàn). */
  myId() {
    const me = api.getCurrentUser();
    return me ? Number(me.id) : null;
  },

  /** Tìm thông tin participant (full_name, avatar...) theo userId. */
  participantInfo(userId) {
    if (!this.call) return null;
    return (
      this.call.participants.find((p) => Number(p.id) === Number(userId)) || null
    );
  },

  /** Danh sách userId đang active trong cuộc gọi, TRỪ chính mình. */
  otherActiveIds() {
    if (!this.call) return [];
    const me = this.myId();
    return (this.call.active_participant_ids || []).filter(
      (id) => Number(id) !== me
    );
  },

  /** Nhãn hiển thị tiếng Việt cho loại cuộc gọi. */
  kindLabel(kind) {
    return kind === "AUDIO" ? "thoại" : "video";
  },

  /**
   * Tải cấu hình ICE (STUN/TURN) từ server.
   *
   * QUAN TRỌNG: mảng rỗng KHÔNG tính là đã tải xong.
   * Lý do: nếu lần đầu gọi lúc chưa đăng nhập, API trả 401 → iceServers = [].
   * Nếu coi [] là hợp lệ thì sẽ không bao giờ thử tải lại → cuộc gọi sau
   * không có ICE server nào → không kết nối được.
   * Vì vậy: chỉ cache khi có phần tử; lỗi → set null để lần sau thử lại.
   */
  async loadConfig() {
    if (this.iceServers && this.iceServers.length) return;
    try {
      const cfg = await api.getCallConfig();
      this.iceServers = cfg.ice_servers || [];
      this.ringTimeoutSeconds = cfg.ring_timeout_seconds || 30;
      this.maxGroupParticipants = cfg.max_group_participants || 6;
    } catch {
      this.iceServers = null; // để lần sau tải lại
    }
  },

  /**
   * Kiểm tra trình duyệt có hỗ trợ media không.
   * Bắt buộc secure context (HTTPS hoặc localhost) — getUserMedia chỉ chạy
   * trong secure context theo spec W3C.
   */
  mediaSupported() {
    if (
      !window.isSecureContext ||
      !navigator.mediaDevices ||
      !window.RTCPeerConnection
    ) {
      toast(
        "Cần mở trang qua HTTPS (hoặc localhost) để dùng micro/camera",
        "error"
      );
      return false;
    }
    return true;
  },

  /**
   * Lấy MediaStream từ thiết bị người dùng.
   *
   * Chiến lược fallback:
   *   - VIDEO: thử lấy cả audio+video (720p, facingMode user).
   *            Nếu fail (không có cam / bị chặn) → fallback audio-only.
   *   - AUDIO: chỉ lấy audio; nếu fail → throw lỗi rõ ràng.
   *
   * Các constraint `echoCancellation`, `noiseSuppression`, `autoGainControl`
   * giúp cuộc gọi thoại nghe rõ hơn (loại echo, tiếng ồn, cân âm lượng).
   */
  async getMedia(kind) {
    const audio = {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    };

    // VIDEO: thử video + audio trước
    if (kind === "VIDEO") {
      try {
        return await navigator.mediaDevices.getUserMedia({
          audio,
          video: {
            width: { ideal: 1280 },
            height: { ideal: 720 },
            facingMode: "user",
          },
        });
      } catch {
        // Fallback: chỉ audio (ví dụ máy không có cam)
        toast("Không mở được camera, chuyển sang chỉ dùng micro", "error");
      }
    }

    // AUDIO: chỉ audio
    try {
      return await navigator.mediaDevices.getUserMedia({ audio, video: false });
    } catch (err) {
      const reason =
        err && err.name === "NotAllowedError"
          ? "bạn đã chặn quyền truy cập micro"
          : "không tìm thấy micro";
      throw new Error(`Không gọi được: ${reason}`);
    }
  },

  // ===========================================================================
  // GỌI 1-1: BÊN GỌI (CALLER)
  // ===========================================================================

  /**
   * Bắt đầu cuộc gọi 1-1 tới `userId`.
   *
   * Trình tự:
   *   1. Kiểm tra đang bận / có phòng / hỗ trợ media.
   *   2. Tải cấu hình ICE.
   *   3. Lấy local media (mic/cam).
   *   4. Gọi API server để tạo cuộc gọi (server sẽ phát `call.incoming`
   *      tới người nhận).
   *   5. Render UI "outgoing", phát ringback, đặt timeout tự hủy.
   *
   * Nếu bước 3 hoặc 4 fail → giải phóng media và thoát êm, không để rác.
   */
  async startCall(userId, kind = "VIDEO") {
    if (this.isBusy()) {
      toast("Bạn đang trong một cuộc gọi khác", "error");
      return;
    }
    if (!currentRoom || !this.mediaSupported()) return;
    await this.loadConfig();

    // Lấy media TRƯỚC khi báo server — nếu user từ chối quyền thì hủy sớm
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
      this.stopLocalStream(); // dọn dẹp nếu server từ chối
      toast(err.message, "error");
      return;
    }

    this.call = call;
    this.role = "caller";
    this.resetControls();
    this.render("outgoing");
    this.playTone("ringback");
    // Hết thời gian đổ chuông mà không ai nghe → tự hủy (missed=true)
    this.ringTimer = setTimeout(
      () => this.hangup(true),
      this.ringTimeoutSeconds * 1000
    );
  },

  /**
   * Xử lý khi người nhận bấm "Nghe" (sự kiện `call.accepted`).
   *
   * Có 2 nhánh:
   *   - CALLEE: tab này không phải tab vừa bấm nghe. Nếu chưa có peer nào
   *     (nghĩa là tab khác đã nhận), teardown + thông báo.
   *   - CALLER: dừng ringback, chuyển UI "connecting", CHỦ ĐỘNG gửi offer
   *     tới callee (đúng quy ước chống glare).
   */
  async onAccepted(call) {
    if (!this.call || call.id !== this.call.id) return;
    this.call = call;

    if (this.role === "callee") {
      // Tab này không phải tab vừa bấm nghe → máy đã được nhận ở nơi khác
      if (!this.peers.size) {
        this.teardown();
        toast("Cuộc gọi đã được trả lời trên thiết bị khác");
      }
      return;
    }

    clearTimeout(this.ringTimer);
    this.stopTone();
    this.render("connecting");

    // Bên gọi chủ động gửi offer (createOffer = true)
    const peerId =
      this.otherActiveIds()[0] ??
      call.participants.find((p) => p.id !== this.myId())?.id;
    if (peerId) await this.ensurePeer(peerId, true);
  },

  // ===========================================================================
  // GỌI 1-1: BÊN NGHE (CALLEE)
  // ===========================================================================

  /**
   * Nhận cuộc gọi đến. Chỉ xử lý nếu:
   *   - Không đang bận cuộc gọi khác.
   *   - Không phải do chính mình khởi tạo (tránh tự gọi mình).
   * Sau đó render UI "incoming", phát nhạc chuông, và hiện notification
   * trình duyệt nếu tab đang ẩn.
   */
  onIncoming(call) {
    if (this.isBusy()) return;
    if (Number(call.initiator_id) === this.myId()) return;
    this.call = call;
    this.role = "callee";
    this.render("incoming");
    this.playTone("ring");
    this.notifyBrowser(call);
  },

  /**
   * Chấp nhận cuộc gọi.
   *
   * THỨ TỰ QUAN TRỌNG: dựng peer (ensurePeer) TRƯỚC khi gọi API acceptCall.
   * Lý do: server phát `call.accepted` gần như tức thì, và offer từ caller
   * có thể tới TRƯỚC khi request accept trả về. Nếu chưa có peer sẵn,
   * tín hiệu offer sẽ bị mất → kết nối thất bại.
   *
   * createOffer = false vì callee chỉ chờ offer, không tự tạo.
   */
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

    // Dựng sẵn kết nối tới người gọi TRƯỚC khi báo server đã nhận máy
    const callerId = this.call.initiator_id;
    await this.ensurePeer(callerId, false);

    try {
      this.call = await api.acceptCall(this.call.id);
    } catch (err) {
      toast(err.message, "error");
      this.teardown();
    }
  },

  /** Từ chối cuộc gọi: teardown ngay, rồi báo server (không chờ phản hồi). */
  async decline() {
    if (!this.call) return;
    const id = this.call.id;
    this.teardown();
    try {
      await api.declineCall(id);
    } catch {}
  },

  // ===========================================================================
  // GỌI NHÓM (GROUP)
  // ===========================================================================

  /**
   * Bắt đầu cuộc gọi nhóm trong phòng hiện tại.
   *
   * Khác gọi 1-1:
   *   - Không có ringTimer (không đổ chuông).
   *   - connectedAt được set ngay (coi như "đang trong cuộc gọi" từ đầu).
   *   - Không tự tạo peer: người đã ở trong sẽ gửi offer tới mình.
   *
   * Trường hợp đặc biệt: nếu cuộc gọi nhóm ĐÃ tồn tại trong phòng, hàm này
   * vẫn gọi API startGroupCall — server sẽ trả về cuộc gọi đang có (idempotent)
   * và mình join vào.
   */
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

    // Vào cuộc gọi đã có sẵn: người trong đó sẽ gửi offer tới mình,
    // ở đây chỉ cần chờ (không gọi ensurePeer).
    this.updateRoomCallBanner(null);
  },

  /** Tham gia cuộc gọi nhóm đang diễn ra trong phòng (từ banner). */
  async joinRoomCall() {
    const target = this.roomCall;
    if (!target) return;
    await this.startGroupCall(target.kind);
  },

  /** Rời cuộc gọi nhóm (khác hangup 1-1: chỉ cần leave, không end). */
  async leaveCall() {
    if (!this.call) return;
    const id = this.call.id;
    this.teardown();
    try {
      await api.leaveCall(id);
    } catch {}
  },

  /**
   * Có người mới tham gia cuộc gọi nhóm.
   *
   * Vì mình ĐÃ Ở TRONG → mình là bên chủ động gửi offer (createOffer = true)
   * theo đúng quy ước chống glare.
   */
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

  /** Có người rời cuộc gọi nhóm: đóng peer, thông báo, render lại. */
  onParticipantLeft(data) {
    if (!this.call || data.call_id !== this.call.id) return;
    this.call = data.call || this.call;
    const gone = Number(data.user_id);
    this.closePeer(gone);

    const info = this.participantInfo(gone);
    if (info) toast(`${info.full_name} đã rời cuộc gọi`);

    // Nếu cuộc gọi không còn ACTIVE (ví dụ chỉ còn 1 người) → tự kết thúc
    if (this.call.status !== "ACTIVE") {
      this.teardown();
      return;
    }
    this.render("group");
  },

  // ===========================================================================
  // BANNER CUỘC GỌI NHÓM CỦA PHÒNG
  // ===========================================================================
  // Khi có cuộc gọi nhóm đang diễn ra trong phòng, hiện banner ở đầu khung
  // chat để mọi người biết mà tham gia.

  /** Truy vấn server xem phòng hiện tại có cuộc gọi nhóm nào đang chạy không. */
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

  /** Xử lý sự kiện realtime room_started / room_updated / room_ended. */
  onRoomCallEvent(call, ended = false) {
    if (!currentRoom || !call || call.room_id !== currentRoom.id) return;
    this.updateRoomCallBanner(ended ? null : call);
  },

  /**
   * Cập nhật banner HTML.
   *
   * Ẩn banner khi:
   *   - Không có cuộc gọi nhóm nào, HOẶC
   *   - Mình đang ở TRONG chính cuộc gọi đó (không cần mời tham gia nữa).
   *
   * Hiện banner với: số người, tên những người đang trong, nút "Tham gia".
   */
  updateRoomCallBanner(call) {
    this.roomCall = call && call.status === "ACTIVE" ? call : null;
    const el = document.getElementById("room-call-banner");
    if (!el) return;

    // Đang ở trong chính cuộc gọi đó thì không cần mời tham gia nữa
    const inThisCall =
      this.call && this.roomCall && this.call.id === this.roomCall.id;
    if (!this.roomCall || inThisCall) {
      el.classList.add("hidden");
      el.innerHTML = "";
      return;
    }

    const n = (this.roomCall.active_participant_ids || []).length;
    const names = (this.roomCall.participants || [])
      .filter((p) =>
        (this.roomCall.active_participant_ids || []).includes(p.id)
      )
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
          <div class="text-[11px] text-emerald-700/70 dark:text-emerald-300/70 truncate">${escapeHtml(
            names.join(", ")
          )}</div>
        </div>
        <button onclick="callUI.joinRoomCall()"
          class="shrink-0 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg transition">
          Tham gia
        </button>
      </div>`;
  },

  // ===========================================================================
  // WEBRTC — NHIỀU KẾT NỐI (MESH)
  // ===========================================================================

  /**
   * Đảm bảo có RTCPeerConnection tới `userId`.
   *
   * Nếu peer đã tồn tại → trả về luôn (idempotent).
   * Nếu chưa → tạo mới, gắn local track, đăng ký handler:
   *   - onicecandidate: gửi ICE candidate cho đối phương qua WebSocket.
   *   - ontrack:        nhận MediaStream từ đối phương, gắn vào UI.
   *   - onconnectionstatechange: xử lý connected/failed.
   *
   * QUAN TRỌNG — flush pendingSignals:
   * Tín hiệu (offer/answer/ice) có thể tới TRƯỚC khi peer được tạo xong.
   * Những tín hiệu đó được xếp hàng trong `pendingSignals`, và sau khi peer
   * sẵn sàng thì xử lý ngay — tránh mất tín hiệu.
   *
   * @param {number}  userId       ID người cần kết nối
   * @param {boolean} createOffer  true = chủ động gửi offer (bên đã ở trong call)
   */
  async ensurePeer(userId, createOffer) {
    userId = Number(userId);
    if (this.peers.has(userId)) return this.peers.get(userId);

    const pc = new RTCPeerConnection({
      iceServers: this.iceServers || [],
      // Chỉ áp iceTransportPolicy khi bật chế độ thử TURN
      ...(FORCE_RELAY ? { iceTransportPolicy: "relay" } : {}),
    });
    const peer = { pc, stream: null, pendingSignals: [], pendingIce: [] };
    this.peers.set(userId, peer);

    // Gắn track cục bộ vào connection (mic + cam)
    if (this.localStream) {
      this.localStream
        .getTracks()
        .forEach((t) => pc.addTrack(t, this.localStream));
    }

    // Gửi ICE candidate cho đối phương mỗi khi tìm được candidate mới
    pc.onicecandidate = (e) => {
      if (e.candidate && this.call) {
        realtime.sendCallSignal(this.call.id, userId, {
          type: "ice",
          candidate: e.candidate.toJSON(),
        });
      }
    };

    // Nhận media từ đối phương
    pc.ontrack = (e) => {
      peer.stream = e.streams[0];
      this.attachRemoteStream(userId, peer.stream);
      // onmute/onunmute: khi track bị tắt/mở (ví dụ peer tắt cam)
      e.track.onmute = () => this.updateTileVisibility(userId);
      e.track.onunmute = () => this.updateTileVisibility(userId);
    };

    pc.onconnectionstatechange = () => {
      const state = pc.connectionState;
      if (state === "connected") {
        this.detectPath(userId);
        // Người mới vào cần biết ngay mình đang tắt camera hay micro
        this.broadcastMediaState(userId);
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
          toast(
            `Mất kết nối với ${info ? info.full_name : "một người"}`,
            "error"
          );
          this.closePeer(userId);
          this.render("group");
        } else {
          // 1-1: hỏng = kết thúc cả cuộc gọi
          toast(
            "Không kết nối được tới người bên kia (mạng chặn kết nối trực tiếp)",
            "error"
          );
          this.hangup();
        }
      }
    };

    // Xử lý các tín hiệu đã tới trước khi kết nối kịp dựng xong
    const queued = peer.pendingSignals.splice(0);
    for (const s of queued) await this.handleSignal(userId, s);

    // Chủ động gửi offer nếu được yêu cầu (bên đã ở trong call)
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

  /**
   * Broadcast trạng thái mic/cam của mình cho các peer.
   *
   * TẠI SAO CẦN?
   * Trình duyệt không tự báo khi peer tắt camera — nó vẫn gửi khung hình đen.
   * Muốn hiện avatar thay vì ô đen, phải để peer tự báo trạng thái.
   *
   * @param {number|null} onlyUserId  null = gửi cho tất cả; ngược lại chỉ 1 người
   */
  broadcastMediaState(onlyUserId = null) {
    if (!this.call) return;
    const signal = { type: "media", camera: this.camOn, mic: this.micOn };
    const targets =
      onlyUserId !== null
        ? [Number(onlyUserId)]
        : Array.from(this.peers.keys());
    targets.forEach((uid) => realtime.sendCallSignal(this.call.id, uid, signal));
  },

  /**
   * Đóng peer: hủy handler (tránh callback rò rỉ), close pc, xóa state,
   * xóa tile khỏi DOM.
   */
  closePeer(userId) {
    userId = Number(userId);
    const peer = this.peers.get(userId);
    if (!peer) return;
    peer.pc.ontrack = null;
    peer.pc.onicecandidate = null;
    peer.pc.onconnectionstatechange = null;
    try {
      peer.pc.close();
    } catch {}
    this.peers.delete(userId);
    this.paths.delete(userId);
    this.peerMedia.delete(userId);
    const tile = document.getElementById(`call-tile-${userId}`);
    if (tile) tile.remove();
  },

  /**
   * Phát hiện media đang đi THẲNG hay qua TURN.
   *
   * CÁCH HOẠT ĐỘNG
   * --------------
   * Dùng `pc.getStats()` để đọc thống kê WebRTC:
   *   - Tìm cặp candidate đang được dùng (nominated hoặc succeeded).
   *   - Tra cứu local-candidate và remote-candidate tương ứng.
   *   - Nếu MỘT trong hai là `relay` → media đang qua TURN.
   *
   * TẠI SAO QUAN TRỌNG?
   * Nhìn bề ngoài, direct và relay giống hệt nhau. Nhưng relay tốn băng thông
   * dịch vụ TURN và tăng độ trễ. Biết điều này giúp chẩn đoán khi gọi qua
   * Internet — vì nhìn bề ngoài hai trường hợp giống hệt nhau.
   */
  async detectPath(userId) {
    const peer = this.peers.get(Number(userId));
    if (!peer) return;
    try {
      const stats = await peer.pc.getStats();
      let pair = null;
      const candidates = new Map();

      stats.forEach((r) => {
        // Lưu tất cả candidate để tra cứu sau
        if (r.type === "local-candidate" || r.type === "remote-candidate") {
          candidates.set(r.id, r);
        }
        // Cặp candidate đang được dùng
        if (
          r.type === "candidate-pair" &&
          (r.nominated || r.state === "succeeded")
        ) {
          pair = r;
        }
      });

      if (!pair) return;
      const local = candidates.get(pair.localCandidateId);
      const remote = candidates.get(pair.remoteCandidateId);

      // Nếu MỘT trong hai đầu là relay → toàn bộ media đang qua TURN
      const isRelay = [local, remote].some(
        (c) => c && c.candidateType === "relay"
      );

      this.paths.set(Number(userId), isRelay ? "relay" : "direct");
      this.renderPath();
    } catch {
      // Không đọc được thống kê thì thôi, không ảnh hưởng cuộc gọi
    }
  },

  /** Hiển thị nhãn đường đi media (direct/relay) trên UI. */
  renderPath() {
    const el = document.getElementById("call-path");
    if (!el || !this.paths.size) return;

    const values = Array.from(this.paths.values());
    const relays = values.filter((v) => v === "relay").length;

    if (relays === 0) {
      el.textContent = "Kết nối trực tiếp giữa các máy";
      el.className = "text-[11px] text-emerald-400/80 mt-0.5";
    } else if (relays === values.length) {
      el.textContent = "Đang chuyển tiếp qua máy chủ trung gian (TURN)";
      el.className = "text-[11px] text-amber-400/80 mt-0.5";
    } else {
      el.textContent = `${relays}/${values.length} kết nối phải đi qua máy chủ trung gian`;
      el.className = "text-[11px] text-amber-400/80 mt-0.5";
    }
  },

  /**
   * Nhận tín hiệu WebRTC từ một peer (qua WebSocket).
   *
   * Nếu chưa có peer:
   *   - Chỉ chấp nhận nếu là OFFER (bên kia chủ động) → tạo peer rồi xử lý.
   *   - Các loại khác (answer/ice) bỏ qua vì chưa có gì để gắn vào.
   *
   * Nếu đã có peer → chuyển thẳng cho handleSignal.
   */
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

  /**
   * Xử lý tín hiệu WebRTC theo từng loại:
   *   - offer:  setRemoteDescription → flush ICE → createAnswer → gửi answer
   *   - answer: setRemoteDescription → flush ICE
   *   - media:  cập nhật trạng thái cam/mic của peer → render lại tile
   *   - ice:    addIceCandidate (hoặc xếp hàng nếu chưa có remoteDescription)
   */
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
      } else if (signal.type === "media") {
        // Peer báo trạng thái cam/mic của họ
        this.peerMedia.set(Number(userId), {
          camera: signal.camera !== false,
          mic: signal.mic !== false,
        });
        this.updateTileVisibility(userId);
      } else if (signal.type === "ice" && signal.candidate) {
        // ICE đến trước remoteDescription phải xếp hàng chờ
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

  /**
   * Đẩy toàn bộ ICE candidate đang xếp hàng vào pc.
   * Gọi sau khi setRemoteDescription thành công.
   */
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

  // ===========================================================================
  // KẾT THÚC CUỘC GỌI
  // ===========================================================================

  /**
   * Kết thúc cuộc gọi.
   *
   * - Nhóm: chỉ cần leave (người khác vẫn tiếp tục).
   * - 1-1: teardown rồi báo server end.
   *
   * @param {boolean} missed  true nếu do hết thời gian đổ chuông
   */
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

  /**
   * Xử lý sự kiện `call.ended` từ server.
   * Hiển thị thông báo phù hợp theo trạng thái cuộc gọi:
   * REJECTED / MISSED / CANCELED / ENDED.
   */
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
      REJECTED: wasCaller
        ? "Người nhận đã từ chối cuộc gọi"
        : "Đã từ chối cuộc gọi",
      MISSED: wasCaller
        ? "Không có người nghe máy"
        : "Bạn có một cuộc gọi nhỡ",
      CANCELED: wasCaller
        ? "Đã hủy cuộc gọi"
        : "Người gọi đã hủy cuộc gọi",
      ENDED: `Cuộc gọi kết thúc${
        duration != null ? " · " + this.formatDuration(duration) : ""
      }`,
    };
    toast(messages[call.status] || "Cuộc gọi kết thúc");
  },

  /**
   * Dọn dẹp toàn bộ tài nguyên cuộc gọi:
   *   - Hủy timer (ring, duration), dừng âm thanh.
   *   - Đóng tất cả peer, dừng local stream.
   *   - Reset state, xóa DOM cuộc gọi.
   *   - Refresh banner phòng (có thể cuộc gọi nhóm vẫn đang chạy).
   */
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
    this.paths.clear();
    this.peerMedia.clear();
    document.getElementById("call-root").innerHTML = "";
    this.refreshRoomCall();
  },

  /** Dừng tất cả track của localStream (tắt đèn cam, nhả mic). */
  stopLocalStream() {
    if (this.localStream) {
      this.localStream.getTracks().forEach((t) => t.stop());
      this.localStream = null;
    }
  },

  // ===========================================================================
  // ĐIỀU KHIỂN MIC / CAMERA
  // ===========================================================================

  /** Reset trạng thái điều khiển về mặc định (bật cả mic lẫn cam). */
  resetControls() {
    this.micOn = true;
    this.camOn = true;
  },

  /**
   * Bật/tắt micro.
   * Dùng `track.enabled` (không phải stop track) để giữ kết nối WebRTC —
   * tắt bằng enabled chỉ mute track, peer vẫn thấy kết nối sống.
   */
  toggleMic() {
    if (!this.localStream) return;
    this.micOn = !this.micOn;
    this.localStream.getAudioTracks().forEach((t) => (t.enabled = this.micOn));
    this.renderControls();
    this.broadcastMediaState();
  },

  /**
   * Bật/tắt camera.
   * Tương tự toggleMic: dùng `enabled` để giữ track sống.
   * Nếu cuộc gọi không có video track → thông báo.
   */
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
    this.broadcastMediaState();
  },

  // ===========================================================================
  // ÂM BÁO (Web Audio API)
  // ===========================================================================

  /**
   * Phát âm thanh đổ chuông (ring) hoặc ringback bằng Web Audio API.
   *
   * Cách tạo tiếng beep:
   *   - OscillatorNode: tạo sóng sine tần số 880Hz (ring) hoặc 440Hz (ringback).
   *   - GainNode: envelope tăng nhanh rồi giảm dần (tránh tiếng "pop").
   *   - Lặp lại bằng setInterval.
   *
   * @param {"ring"|"ringback"} type
   */
  playTone(type) {
    this.stopTone();
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const beep = () => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.frequency.value = type === "ring" ? 880 : 440;
        // Envelope: tăng từ ~0 lên 0.15 rồi giảm về ~0 (tránh click/pop)
        gain.gain.setValueAtTime(0.0001, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.9);
        osc.connect(gain).connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 1);
      };
      beep();
      this.tone = {
        ctx,
        timer: setInterval(beep, type === "ring" ? 1500 : 3000),
      };
    } catch {
      this.tone = null;
    }
  },

  /** Dừng âm thanh đang phát và giải phóng AudioContext. */
  stopTone() {
    if (!this.tone) return;
    clearInterval(this.tone.timer);
    try {
      this.tone.ctx.close();
    } catch {}
    this.tone = null;
  },

  /**
   * Hiện notification trình duyệt khi có cuộc gọi đến mà tab đang ẩn.
   *
   * Chỉ hoạt động khi tab hidden (document.hidden) — tránh spam notification
   * khi user đang nhìn thấy UI cuộc gọi.
   * Yêu cầu quyền Notification; nếu chưa có thì xin (không xin nếu đã denied).
   */
  notifyBrowser(call) {
    if (!document.hidden || !("Notification" in window)) return;
    const caller = call.participants.find((p) => p.id === call.initiator_id);
    const show = () => {
      try {
        new Notification("Cuộc gọi đến", {
          body: `${
            caller ? caller.full_name : "Ai đó"
          } đang gọi ${this.kindLabel(call.kind)} cho bạn`,
        });
      } catch {}
    };
    if (Notification.permission === "granted") show();
    else if (Notification.permission !== "denied")
      Notification.requestPermission().then((p) => p === "granted" && show());
  },

  // ===========================================================================
  // ĐỒNG HỒ THỜI LƯỢNG CUỘC GỌI
  // ===========================================================================

  /** Format giây thành "MM:SS". */
  formatDuration(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  },

  /**
   * Bắt đầu đồng hồ đếm thời lượng cuộc gọi.
   * Cập nhật mỗi giây vào element #call-status.
   */
  startDurationTimer() {
    clearInterval(this.durationTimer);
    const tick = () => {
      if (!this.connectedAt) return;
      this.setStatusText(
        this.formatDuration(
          Math.floor((Date.now() - this.connectedAt) / 1000)
        )
      );
    };
    tick();
    this.durationTimer = setInterval(tick, 1000);
  },

  /** Ghi text vào element #call-status (nếu tồn tại). */
  setStatusText(text) {
    const el = document.getElementById("call-status");
    if (el) el.textContent = text;
  },

  // ===========================================================================
  // GIAO DIỆN — RENDER
  // ===========================================================================

  /**
   * Gắn MediaStream nhận từ peer vào thẻ <video> tương ứng.
   * Kiểm tra `srcObject !== stream` để tránh gán lại (gây nháy hình).
   */
  attachRemoteStream(userId, stream) {
    const video = document.getElementById(`call-video-${userId}`);
    if (video && video.srcObject !== stream) {
      video.srcObject = stream;
      video.play().catch(() => {});
    }
    this.updateTileVisibility(userId);
  },

  /**
   * Cập nhật hiển thị của tile (ô video) cho một người.
   *
   * Logic:
   *   - Nếu là CHÍNH MÌNH: dựa vào track video cục bộ + cờ camOn.
   *   - Nếu là NGƯỜI KHÁC: dựa vào peerMedia (peer tự báo) + track thực tế.
   *
   * TẠI SAO CẦN peerMedia?
   * Khi peer tắt cam, trình duyệt vẫn gửi khung hình đen — track vẫn "live".
   * Muốn biết peer đã tắt cam phải dựa vào signal `media` họ gửi.
   *
   * Hiển thị:
   *   - Có video → hiện <video>, ẩn placeholder avatar.
   *   - Không video → ẩn <video>, hiện avatar.
   *   - Mic tắt → hiện badge 🔇.
   */
  updateTileVisibility(userId) {
    const video = document.getElementById(`call-video-${userId}`);
    const holder = document.getElementById(`call-placeholder-${userId}`);
    if (!video || !holder) return;

    let hasVideo;
    let micOn = true;

    if (Number(userId) === this.myId()) {
      // Bản thân: dựa vào track cục bộ
      hasVideo =
        this.localStream &&
        this.localStream.getVideoTracks().some((t) => t.enabled);
      micOn = this.micOn;
    } else {
      // Người khác: kết hợp peerMedia (peer báo) và track thực tế
      const peer = this.peers.get(Number(userId));
      const state = this.peerMedia.get(Number(userId));
      const cameraOn = !state || state.camera !== false;
      micOn = !state || state.mic !== false;
      hasVideo =
        cameraOn &&
        peer &&
        peer.stream &&
        peer.stream
          .getVideoTracks()
          .some((t) => t.readyState === "live" && !t.muted);
    }

    video.classList.toggle("invisible", !hasVideo);
    holder.classList.toggle("hidden", !!hasVideo);

    const micBadge = document.getElementById(`call-mic-${userId}`);
    if (micBadge) micBadge.classList.toggle("hidden", micOn);
  },

  /**
   * Tạo HTML cho một nút điều khiển tròn.
   *
   * @param {string}  onclick  Biểu thức JS chạy khi bấm
   * @param {string}  icon     Emoji/icon
   * @param {string}  label    Tooltip
   * @param {boolean} active   true = đang bật (nền mờ), false = đang tắt (nền trắng)
   * @param {boolean} danger   true = nút đỏ (kết thúc cuộc gọi)
   */
  controlButton(onclick, icon, label, active, danger = false) {
    const cls = danger
      ? "bg-red-600 hover:bg-red-700 text-white"
      : active
      ? "bg-white/15 hover:bg-white/25 text-white"
      : "bg-white text-slate-900 hover:bg-slate-200";
    return `<button onclick="${onclick}" title="${label}"
      class="w-14 h-14 rounded-full flex items-center justify-center text-xl transition shadow-lg ${cls}">${icon}</button>`;
  },

  /** Render thanh điều khiển (mic, cam, kết thúc). */
  renderControls() {
    const bar = document.getElementById("call-controls");
    if (!bar) return;
    const hasCam =
      this.localStream && this.localStream.getVideoTracks().length > 0;
    const leaveLabel = this.isGroup() ? "Rời cuộc gọi" : "Kết thúc";
    bar.innerHTML = `
      ${this.controlButton(
        "callUI.toggleMic()",
        this.micOn ? "🎤" : "🔇",
        this.micOn ? "Tắt micro" : "Bật micro",
        this.micOn
      )}
      ${
        hasCam
          ? this.controlButton(
              "callUI.toggleCam()",
              this.camOn ? "📹" : "🚫",
              this.camOn ? "Tắt camera" : "Bật camera",
              this.camOn
            )
          : ""
      }
      ${this.controlButton(
        "callUI.hangup()",
        "✆",
        leaveLabel,
        false,
        true
      )}
    `;
  },

  /**
   * Tạo HTML cho một ô video trong lưới.
   *
   * @param {object}  user   Thông tin user (id, full_name, avatar_url...)
   * @param {boolean} isMe   true nếu là ô của chính mình
   */
  tile(user, isMe = false) {
    const id = user.id;
    return `<div id="call-tile-${id}" class="relative bg-slate-800 rounded-xl overflow-hidden ring-1 ring-white/10 aspect-video">
      <video id="call-video-${id}" autoplay playsinline ${
      isMe ? "muted" : ""
    }
        class="w-full h-full object-cover invisible ${
          isMe ? "-scale-x-100" : ""
        }"></video>
      <div id="call-placeholder-${id}" class="absolute inset-0 flex items-center justify-center">
        ${renderAvatar(user, 64)}
      </div>
      <div class="absolute bottom-1.5 left-2 right-2 flex items-center gap-1.5 text-[11px] text-white/90 drop-shadow">
        <span id="call-mic-${id}" class="hidden shrink-0" title="Đang tắt micro">🔇</span>
        <span class="truncate">${escapeHtml(user.full_name)}${
      isMe ? " (bạn)" : ""
    }</span>
      </div>
    </div>`;
  },

  /**
   * Render UI cuộc gọi theo "stage".
   *
   * Các stage:
   *   - "incoming":   modal cuộc gọi đến (1-1)
   *   - "outgoing":   đang gọi (1-1)
   *   - "connecting": đang kết nối (1-1)
   *   - "active":     đang trong cuộc gọi (1-1)
   *   - "group":      đang trong cuộc gọi nhóm
   *
   * TỐI ƯU: nếu #call-stage đã tồn tại, chỉ vẽ lại lưới + status + controls
   * (không dựng lại toàn bộ DOM) — giữ nguyên thẻ <video> đang phát để
   * không làm ngắt video.
   */
  render(stage) {
    const root = document.getElementById("call-root");
    if (!this.call) return;

    // --- Cuộc gọi 1-1 đang đổ chuông ---
    if (stage === "incoming") {
      const peer = this.participantInfo(this.call.initiator_id) || {
        id: this.call.initiator_id,
        full_name: "Người dùng",
      };
      root.innerHTML = `
        <div class="fixed inset-0 z-[45] flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm">
          <div class="w-full max-w-xs bg-white dark:bg-slate-900 rounded-3xl shadow-2xl p-6 text-center">
            <div class="flex justify-center mb-4">
              <div class="rounded-full ring-4 ring-emerald-400/60 animate-pulse">${renderAvatar(
                peer,
                88
              )}</div>
            </div>
            <div class="font-bold text-lg text-slate-900 dark:text-slate-100 truncate">${escapeHtml(
              peer.full_name
            )}</div>
            <div class="text-sm text-slate-500 dark:text-slate-400 mt-1">Cuộc gọi ${this.kindLabel(
              this.call.kind
            )} đến...</div>
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

    // Xác định text trạng thái và tiêu đề
    const statusText =
      { outgoing: "Đang gọi...", connecting: "Đang kết nối..." }[stage] || "";
    const title = this.isGroup()
      ? `${currentRoom ? "# " + currentRoom.name : "Cuộc gọi nhóm"}`
      : escapeHtml(
          (
            this.participantInfo(this.otherActiveIds()[0]) ||
            this.call.participants.find((p) => p.id !== this.myId()) || {
              full_name: "Người dùng",
            }
          ).full_name
        );

    const me = api.getCurrentUser() || {};
    const meTile = {
      id: this.myId(),
      full_name: me.full_name || "Tôi",
      avatar_url: me.avatar_url,
      username: me.username,
    };
    const others = this.otherActiveIds().map(
      (id) =>
        this.participantInfo(id) || { id, full_name: `Người dùng #${id}` }
    );

    // Thông báo "đang chờ" cho cuộc gọi nhóm khi chưa có ai khác
    const waiting =
      this.isGroup() && others.length === 0
        ? `<div class="absolute inset-x-0 bottom-28 text-center text-sm text-white/60">Đang chờ người khác tham gia...</div>`
        : "";

    // Nếu stage đã tồn tại: chỉ cập nhật phần thay đổi
    const existing = document.getElementById("call-stage");
    if (existing) {
      this.renderGrid(meTile, others);
      this.setStatusText(statusText || this.statusFallback());
      this.renderControls();
      const w = document.getElementById("call-waiting");
      if (w) w.innerHTML = waiting;
      return;
    }

    // Dựng toàn bộ stage lần đầu
    root.innerHTML = `
      <div id="call-stage" class="fixed inset-0 z-[45] bg-slate-950 text-white flex flex-col">
        ${
          FORCE_RELAY
            ? `
        <div class="shrink-0 bg-amber-500/90 text-slate-900 text-xs text-center py-1.5 px-4 font-medium">
          Chế độ thử TURN đang bật · mọi cuộc gọi bị ép đi qua máy chủ trung gian ·
          bỏ <span class="font-mono">?relay=1</span> khỏi địa chỉ để tắt
        </div>`
            : ""
        }
        <div class="pt-6 pb-3 text-center shrink-0">
          <div class="text-lg font-semibold truncate px-4">${title}</div>
          <div id="call-status" class="text-sm text-white/70 mt-1 h-5">${statusText}</div>
          <div class="text-[11px] text-white/40 mt-0.5">
            Cuộc gọi ${this.kindLabel(this.call.kind)}${
      this.isGroup() ? " nhóm" : ""
    } · WebRTC
          </div>
          <div id="call-path" class="text-[11px] text-white/40 mt-0.5"></div>
        </div>

        <div id="call-grid" class="flex-1 min-h-0 px-4 pb-2 overflow-y-auto scroll-thin"></div>
        <div id="call-waiting" class="relative">${waiting}</div>

        <div id="call-controls" class="shrink-0 pb-8 pt-4 flex justify-center gap-5"></div>
      </div>`;

    this.renderGrid(meTile, others);
    this.renderControls();
    this.renderPath();
  },

  /** Text trạng thái dự phòng: đồng hồ thời lượng (nếu đã kết nối). */
  statusFallback() {
    return this.connectedAt
      ? this.formatDuration(
          Math.floor((Date.now() - this.connectedAt) / 1000)
        )
      : "";
  },

  /**
   * Render lưới video.
   *
   * TỐI ƯU QUAN TRỌNG:
   *   - Không dựng lại toàn bộ grid mỗi lần render.
   *   - Chỉ XÓA tile của người đã rời, THÊM tile của người mới.
   *   - Giữ nguyên tile đang có → tránh ngắt video (gán lại srcObject làm
   *     video nháy đen).
   *
   * Số cột:
   *   - 1 người: 1 cột
   *   - 2-4 người: 2 cột
   *   - >4 người: 3 cột
   */
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

    // Thêm ô còn thiếu, KHÔNG đụng vào ô đã có để video không bị ngắt
    wanted.forEach((u) => {
      if (!document.getElementById(`call-tile-${u.id}`)) {
        grid.insertAdjacentHTML(
          "beforeend",
          this.tile(u, Number(u.id) === this.myId())
        );
        if (Number(u.id) === this.myId()) {
          // Ô của mình: gắn local stream
          const v = document.getElementById(`call-video-${u.id}`);
          if (v && this.localStream) v.srcObject = this.localStream;
        } else {
          // Ô người khác: gắn remote stream nếu đã có
          const peer = this.peers.get(Number(u.id));
          if (peer && peer.stream) this.attachRemoteStream(u.id, peer.stream);
        }
        this.updateTileVisibility(u.id);
      }
    });
  },
};

// ===========================================================================
// ĐĂNG KÝ SỰ KIỆN REALTIME (từ WebSocket)
// ===========================================================================
// Mọi sự kiện cuộc gọi từ server đều được route vào callUI.

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

// ===========================================================================
// KHỞI TẠO CHẾ ĐỘ THỬ TURN
// ===========================================================================
// Bật chế độ thử TURN: báo ngay khi mở trang, và cảnh báo nếu chưa cấu hình TURN
if (FORCE_RELAY) {
  window.addEventListener("DOMContentLoaded", () => {
    toast("Chế độ thử TURN: mọi cuộc gọi sẽ đi qua máy chủ trung gian");

    // Chỉ kiểm tra được cấu hình sau khi đã đăng nhập, vì endpoint cần token
    if (!api.getToken()) return;

    callUI.loadConfig().then(() => {
      const hasTurn = (callUI.iceServers || []).some(
        (s) => String(s.urls).includes("turn") && s.username
      );
      if (!hasTurn) {
        toast(
          "Chưa cấu hình TURN -- ở chế độ này cuộc gọi sẽ không kết nối được",
          "error"
        );
      }
    });
  });
}

// ===========================================================================
// DỌN DẸP KHI ĐÓNG TAB
// ===========================================================================
// Đóng tab giữa cuộc gọi: server tự dọn khi WebSocket ngắt,
// ở đây chỉ cần giải phóng camera/micro để tắt đèn cam ngay lập tức.
window.addEventListener("pagehide", () => callUI.stopLocalStream());
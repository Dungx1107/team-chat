/** GROUP media only. DIRECT keeps the existing P2P implementation in call.js. */
class GroupSfuTransport {
  constructor({ sdk = globalThis.LivekitClient, onChange = () => {}, onDisconnected = () => {}, onAudioBlocked = () => {} } = {}) {
    if (!sdk) throw new Error("Không tải được thư viện cuộc gọi nhóm. Hãy tải lại trang.");
    this.sdk = sdk;
    this.onChange = onChange;
    this.onDisconnected = onDisconnected;
    this.onAudioBlocked = onAudioBlocked;
    this.closed = false;
    this.attached = new Map();
    this.room = new sdk.Room({ adaptiveStream: true, dynacast: true });
    const events = sdk.RoomEvent;
    for (const name of ["TrackSubscribed", "TrackUnsubscribed", "TrackMuted", "TrackUnmuted",
      "ParticipantConnected", "ParticipantDisconnected", "LocalTrackPublished", "LocalTrackUnpublished",
      "Reconnecting", "Reconnected"]) {
      this.room.on(events[name], () => { if (!this.closed) this.onChange(); });
    }
    this.room.on(events.AudioPlaybackStatusChanged, () => {
      if (!this.closed && !this.room.canPlaybackAudio) this.onAudioBlocked();
    });
    this.room.on(events.Disconnected, (reason) => {
      if (!this.closed) this.onDisconnected(reason);
    });
  }

  async connect(session, stream) {
    await this.room.connect(session.server_url, session.participant_token);
    if (this.closed) {
      await this.room.disconnect();
      throw new Error("Cuộc gọi đã hủy");
    }
    for (const track of stream.getTracks()) {
      if (this.closed) throw new Error("Cuộc gọi đã hủy");
      const capture = track.getSettings?.() || {};
      const preset = this.sdk.VideoPresets?.[capture.height > 720 ? "h1080" : capture.height > 360 ? "h720" : "h360"];
      await this.room.localParticipant.publishTrack(track, {
        source: track.kind === "audio" ? this.sdk.Track.Source.Microphone : this.sdk.Track.Source.Camera,
        simulcast: track.kind === "video",
        ...(track.kind === "video" ? {
          videoEncoding: { ...preset?.encoding, maxFramerate: capture.frameRate || 30 },
        } : {}),
      });
    }
    if (this.closed) {
      await this.room.disconnect();
      throw new Error("Cuộc gọi đã hủy");
    }
    await this.room.startAudio().catch(() => this.onAudioBlocked());
    this.onChange();
  }

  users() {
    return Array.from(this.room.remoteParticipants.values()).filter(p => /^user-\d+$/.test(p.identity))
      .map(p => ({ id: Number(p.identity.slice(5)), full_name: p.name || p.identity }));
  }

  participant(userId) {
    const identity = `user-${userId}`;
    return this.room.localParticipant.identity === identity ? this.room.localParticipant : this.room.remoteParticipants.get(identity);
  }

  publication(userId, source) {
    const participant = this.participant(userId);
    return participant && Array.from(participant.trackPublications.values()).find(p => p.source === source);
  }

  media(userId) {
    const camera = this.publication(userId, this.sdk.Track.Source.Camera);
    const mic = this.publication(userId, this.sdk.Track.Source.Microphone);
    return { camera: !!(camera && camera.track && !camera.isMuted), mic: !!(mic && !mic.isMuted) };
  }

  attach(userId, video, audio) {
    this.attachTrack(video, this.publication(userId, this.sdk.Track.Source.Camera));
    this.attachTrack(audio, this.publication(userId, this.sdk.Track.Source.Microphone));
  }

  attachTrack(element, publication) {
    if (!element) return;
    const track = publication && publication.track;
    const previous = this.attached.get(element);
    if (previous === track) return;
    if (previous) previous.detach(element);
    if (track) {
      track.attach(element);
      this.attached.set(element, track);
    } else {
      this.attached.delete(element);
      element.srcObject = null;
    }
  }

  pruneAttachments() {
    for (const [element, track] of this.attached) {
      if (!element.isConnected) { track.detach(element); this.attached.delete(element); }
    }
  }

  async setMicEnabled(enabled) {
    await this.room.localParticipant.setMicrophoneEnabled(enabled);
    this.onChange();
  }

  async setCameraEnabled(enabled) {
    await this.room.localParticipant.setCameraEnabled(enabled);
    this.onChange();
  }

  async disconnect() {
    this.closed = true;
    for (const [element, track] of this.attached) track.detach(element);
    this.attached.clear();
    await this.room.disconnect();
  }
}

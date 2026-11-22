/* Authenticated HTTPS signaling, direct WebRTC video, no media relay or recording. */
(() => {
  'use strict';
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  async function request(path, token, options = {}) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(window.SmartShelfApi.apiUrl('/api/rtc' + path), {
        ...options, cache: 'no-store', signal: controller.signal,
        headers: { Authorization: `Bearer ${token}`, ...(options.body ? {'Content-Type': 'application/json'} : {}) }
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const updateRequired = response.status === 404 && (path === '/view' || path.startsWith('/camera/poll'));
        const error = new Error(updateRequired ? 'مسیر سیگنالینگ WebRTC در بک‌اند پیدا نشد؛ نسخه فرانت‌اند و بک‌اند را یکسان نصب کنید. ارسال فریم هوش مصنوعی از WSS/HTTPS مستقل است.' : response.status === 404 ? 'نشست نمایش دوربین پایان یافته؛ اتصال دوباره انجام می‌شود.' : typeof data.detail === 'string' ? data.detail : `خطای اتصال (${response.status})`);
        error.status = response.status; error.updateRequired = updateRequired; throw error;
      }
      return await response.json();
    } finally { clearTimeout(timer); }
  }
  const post = body => ({method: 'POST', body: JSON.stringify(body)});
  const networkHint = 'اتصال مستقیم ویدیو برقرار نشد. تبلت و پنل را روی یک Wi-Fi بگذارید؛ برای شبکه‌های جدا ممکن است سرور TURN لازم باشد.';

  class PeerLink {
    constructor(pc, send) {
      this.pc = pc; this.send = send; this.remoteIce = []; this.localIce = []; this.ready = false; this.chain = Promise.resolve();
      pc.onicecandidate = event => { if (event.candidate) { this.localIce.push(event.candidate.toJSON()); this.flush(); } };
    }
    signal(payload) { const pending = this.chain.then(() => this.send(payload)); this.chain = pending.catch(() => {}); return pending; }
    flush() { if (!this.ready) return; for (const candidate of this.localIce.splice(0)) this.signal({type: 'ice', candidate}).catch(() => {}); }
    async description(type, description) {
      await this.pc.setLocalDescription(description);
      await this.signal({type, description: {type, sdp: this.pc.localDescription.sdp}});
      this.ready = true; this.flush();
    }
    async remote(description) { await this.pc.setRemoteDescription(description); for (const candidate of this.remoteIce.splice(0)) await this.pc.addIceCandidate(candidate); }
    async ice(candidate) { if (!candidate) return; if (this.pc.remoteDescription) await this.pc.addIceCandidate(candidate); else this.remoteIce.push(candidate); }
    close() { this.pc.onicecandidate = null; this.pc.onconnectionstatechange = null; this.pc.close(); }
  }

  class Viewer {
    constructor({video, getToken, onState = () => {}, onStats = () => {}}) {
      Object.assign(this, {video, getToken, onState, onStats});
      this.epoch = 0; this.active = false; this.peer = null; this.sid = null; this.retry = null; this.failures = 0;
      this.control = null; this.controlSeq = 0; this.commands = new Map(); this.deviceId = null;
    }
    start() {
      this.stop(); this.active = true; this.failures = 0;
      this.connect();
    }
    async connect() {
      if (!this.active) return;
      const epoch = ++this.epoch; let sid = null;
      try {
        if (!window.RTCPeerConnection) throw new Error('این مرورگر WebRTC ندارد؛ از Chrome به‌روز استفاده کنید.');
        this.onState('connecting', 'در حال برقراری ویدیوی زنده WebRTC…');
        const token = this.getToken();
        const info = await request('/view', token, post({})); sid = info.session_id;
        if (!this.active || epoch !== this.epoch) { request(`/view/${sid}/signal`, token, post({type: 'close'})).catch(() => {}); return; }
        this.sid = sid; this.sessionToken = token; this.deviceId = info.device_id;
        const pc = new RTCPeerConnection({iceServers: info.ice_servers, bundlePolicy: 'max-bundle'});
        const peer = new PeerLink(pc, payload => request(`/view/${sid}/signal`, token, post(payload))); this.peer = peer;
        pc.addTransceiver('video', {direction: 'recvonly'});
        const channel = pc.createDataChannel('smartshelf-vision', {ordered: true}); this.control = channel;
        channel.onmessage = event => {
          if (epoch !== this.epoch || typeof event.data !== 'string' || event.data.length > 1024) return;
          try {
            const data = JSON.parse(event.data), pending = this.commands.get(data.id);
            if (!pending || data.type !== 'vision_ack' || data.device_id !== this.deviceId) return;
            this.commands.delete(data.id); clearTimeout(pending.timer);
            if (data.error || data.enabled !== pending.enabled) pending.reject(new Error(data.error || 'تبلت فرمان ارسال تصویر را تأیید نکرد.'));
            else pending.resolve(data);
          } catch {}
        };
        pc.ontrack = event => {
          if (epoch !== this.epoch) return;
          this.video.srcObject = event.streams[0] || new MediaStream([event.track]); this.video.muted = true; this.video.playsInline = true;
          this.video.play().catch(() => { if (epoch === this.epoch) this.onState('play', 'برای پخش ویدیو دکمهٔ نمایش دوربین را دوباره بزنید.'); });
        };
        pc.onconnectionstatechange = () => { if (epoch === this.epoch && ['failed', 'closed'].includes(pc.connectionState)) this.failed(new Error(networkHint), epoch); };
        await peer.description('offer', await pc.createOffer());
        let after = 0, lastFrames = 0, lastTime = 0, lastProgress = Date.now(), started = Date.now(), connected = false;
        while (this.active && epoch === this.epoch) {
          const data = await request(`/view/${sid}?after=${after}`, token);
          if (epoch !== this.epoch) break;
          for (const event of data.messages) {
            if (event.seq <= after) continue;
            if (event.type === 'answer') await peer.remote(event.description);
            if (event.type === 'ice') await peer.ice(event.candidate);
            if (event.type === 'close') throw new Error('ارسال ویدیوی تبلت متوقف شد؛ صفحهٔ دوربین تبلت را باز نگه دارید.');
            after = event.seq;
          }
          if (data.closed) throw new Error('نشست ویدیوی تبلت پایان یافت؛ در حال اتصال مجدد…');
          const reports = await pc.getStats();
          reports.forEach(report => {
            if (report.type !== 'inbound-rtp' || (report.kind || report.mediaType) !== 'video') return;
            const frames = report.framesDecoded || 0, elapsed = report.timestamp - lastTime;
            const fps = lastTime && elapsed > 0 ? (frames - lastFrames) * 1000 / elapsed : report.framesPerSecond || 0;
            if (frames > lastFrames) {
              lastProgress = Date.now(); connected = true; this.failures = 0;
              this.onState('live', 'ویدیوی زنده · WebRTC');
              this.onStats({fps, width: report.frameWidth || this.video.videoWidth, height: report.frameHeight || this.video.videoHeight, frames});
            }
            lastFrames = frames; lastTime = report.timestamp;
          });
          if (!connected && Date.now() - started > 20000) throw new Error(networkHint);
          if (connected && Date.now() - lastProgress > 6000) throw new Error('فریم تازه‌ای از تبلت نرسید؛ در حال اتصال مجدد…');
          await sleep(connected ? 1200 : 450);
        }
      } catch (error) { this.failed(error, epoch); }
    }
    failed(error, epoch) {
      if (!this.active || epoch !== this.epoch) return;
      this.release(); this.epoch++; this.failures++;
      this.onStats({fps: 0, width: 0, height: 0, frames: 0});
      this.onState('error', error.message || networkHint);
      if (![401, 403].includes(error.status) && !error.updateRequired && this.failures < 4) this.retry = setTimeout(() => this.connect(), 3500);
    }
    release() {
      clearTimeout(this.retry); this.retry = null;
      for (const pending of this.commands.values()) {clearTimeout(pending.timer);pending.reject(new Error('ارتباط کنترل تبلت قطع شد؛ دوباره تلاش کنید.'));}
      this.commands.clear(); this.control?.close(); this.control = null;
      if (this.sid) request(`/view/${this.sid}/signal`, this.sessionToken, post({type: 'close'})).catch(() => {});
      this.sid = null; this.peer?.close(); this.peer = null;
      this.video.pause(); this.video.srcObject = null;
    }
    stop() { this.active = false; this.epoch++; this.release(); this.onState('stopped', 'نمایش ویدیوی زنده متوقف است.'); }
    async play() { await this.video.play(); }
    async setProcessing(enabled, isCurrent = () => true) {
      const epoch = this.epoch, deadline = Date.now() + 8000;
      while (this.active && epoch === this.epoch && isCurrent() && this.control?.readyState !== 'open' && Date.now() < deadline) await sleep(100);
      if (!this.active || epoch !== this.epoch || !isCurrent()) throw new Error('فرمان قدیمی لغو شد.');
      if (this.control?.readyState !== 'open') throw new Error('کانال کنترل تبلت آماده نیست؛ اتصال ویدیوی زنده را بررسی کنید.');
      const id = `${epoch}-${++this.controlSeq}`;
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {this.commands.delete(id);reject(new Error('فرمان از تبلت تأیید نشد؛ صفحهٔ دوربین تبلت را با نسخهٔ 1.4.1 دوباره باز کنید.'));}, 6000);
        this.commands.set(id, {resolve, reject, timer, enabled});
        try {this.control.send(JSON.stringify({type: 'vision_control', id, enabled}));}
        catch (error) {clearTimeout(timer);this.commands.delete(id);reject(error);}
      });
    }
  }

  class Publisher {
    constructor({deviceId, getToken, onState = () => {}, onControl = null}) {
      Object.assign(this, {deviceId, getToken, onState, onControl}); this.peers = new Map(); this.after = {}; this.stream = null; this.active = false; this.epoch = 0; this.enabled = true;
    }
    async setStream(stream) {
      this.stream = stream;
      for (const [sid, peer] of this.peers) {
        try { const sender = peer.pc.getSenders().find(item => item.track?.kind === 'video'); if (sender) await sender.replaceTrack(stream?.getVideoTracks()[0] || null); }
        catch { this.drop(sid, true); }
      }
    }
    setEnabled(enabled) { this.enabled = enabled; if (!enabled) for (const sid of this.peers.keys()) this.drop(sid, true); }
    async start() {
      if (this.active || !window.RTCPeerConnection) return;
      this.active = true; const epoch = ++this.epoch;
      while (this.active && epoch === this.epoch) {
        try {
          const token = this.getToken();
          if (!token || !this.enabled || !this.stream?.getVideoTracks().some(t => t.readyState === 'live')) { await sleep(1000); continue; }
          const data = await request(`/camera/poll?device_id=${encodeURIComponent(this.deviceId)}`, token, post({after: this.after}));
          if (epoch !== this.epoch) break;
          const active = new Set(data.sessions.map(s => s.session_id));
          for (const sid of this.peers.keys()) if (!active.has(sid)) this.drop(sid);
          for (const sid of Object.keys(this.after)) if (!active.has(sid)) delete this.after[sid];
          for (const session of data.sessions) {
            const sid = session.session_id;
            for (const event of session.messages) {
              if (event.seq <= (this.after[sid] || 0)) continue;
              if (event.type === 'close') this.drop(sid);
              else if (event.type === 'offer' && !session.closed && this.enabled) {
                this.drop(sid);
                const pc = new RTCPeerConnection({iceServers: data.ice_servers, bundlePolicy: 'max-bundle'});
                const peer = new PeerLink(pc, payload => request(`/camera/${sid}/signal?device_id=${encodeURIComponent(this.deviceId)}`, token, post(payload))); this.peers.set(sid, peer);
                pc.ondatachannel = ({channel}) => {
                  if (channel.label !== 'smartshelf-vision') {channel.close();return;}
                  channel.onmessage = async event => {
                    if (this.peers.get(sid) !== peer || !this.active || typeof event.data !== 'string' || event.data.length > 512) return;
                    try {
                      const data = JSON.parse(event.data);
                      if (data.type !== 'vision_control' || typeof data.id !== 'string' || data.id.length > 80 || typeof data.enabled !== 'boolean') return;
                      let reply;
                      try {
                        if (!this.onControl) throw new Error('کنترل ارسال در این صفحه آماده نیست؛ صفحهٔ دوربین تبلت را به‌روز کنید.');
                        reply = await this.onControl(data.enabled);
                        reply = {enabled: reply.enabled};
                      } catch (error) {reply = {error: error.message || 'اجرای فرمان روی تبلت ناموفق بود.'};}
                      if (this.peers.get(sid) === peer && channel.readyState === 'open') channel.send(JSON.stringify({type: 'vision_ack', id: data.id, device_id: this.deviceId, ...reply}));
                    } catch {}
                  };
                };
                pc.onconnectionstatechange = () => {
                  if (pc.connectionState === 'connected') this.onState('live', 'پخش زنده WebRTC برای پنل برقرار است.');
                  if (['failed', 'closed'].includes(pc.connectionState)) this.drop(sid, true);
                };
                await peer.remote(event.description);
                const track = this.stream.getVideoTracks()[0]; track.contentHint = 'motion';
                const sender = pc.addTrack(track, this.stream);
                await peer.description('answer', await pc.createAnswer());
                try { const params = sender.getParameters(); if (params.encodings?.length) { params.encodings[0].maxBitrate = 2500000; params.encodings[0].maxFramerate = 30; params.degradationPreference = 'balanced'; await sender.setParameters(params); } } catch {}
              } else if (event.type === 'ice' && this.peers.has(sid)) await this.peers.get(sid).ice(event.candidate);
              this.after[sid] = event.seq;
            }
            if (session.closed) this.drop(sid);
          }
          if (!this.peers.size) this.onState('ready', 'WebRTC آماده است؛ «نمایش دوربین» را در پنل بزنید.');
          await sleep(this.peers.size ? 600 : 1200);
        } catch (error) {
          if (!this.active || epoch !== this.epoch) break;
          this.onState('error', error.status === 404 ? 'مسیر WebRTC در بک‌اند پیدا نشد؛ پیش‌نمایش JPEG جایگزین را در صفحه فروشگاه بررسی کنید.' : 'ارتباط نمایش زنده قطع شد؛ تلاش مجدد خودکار…');
          await sleep(error.status === 404 ? 15000 : 2500);
        }
      }
    }
    drop(sid, notify = false) { const peer = this.peers.get(sid); if (!peer) return; this.peers.delete(sid); if (notify) peer.signal({type: 'close'}).catch(() => {}); peer.close(); }
    stop() { this.active = false; this.epoch++; for (const sid of this.peers.keys()) this.drop(sid, true); this.after = {}; }
  }
  window.SmartShelfRTC = {Viewer, Publisher};
})();

// SMARTSHELF Camera Sensor Web App

const I18N = {
  fa: {
    sensorRole: "حسگر تبلت",
    connecting: "در حال اتصال...",
    online: "متصل به سرور",
    offline: "قطع ارتباط",
    deviceIdLabel: "شناسه دستگاه:",
    fpsLabel: "نرخ فریم:",
    framesSentLabel: "فریم‌های ارسالی:",
    cameraErrorTitle: "خطا در دسترسی به دوربین",
    cameraErrorDesc: "بازکردن دوربین کامل نشده است. علت دقیق در این بخش نمایش داده می‌شود.",
    retryCameraBtn: "تلاش مجدد",
    selectCamera: "انتخاب دوربین:",
    defaultCamera: "دوربین پیش‌فرض (پشت)",
    pauseStream: "توقف ارسال فریم",
    resumeStream: "شروع ارسال فریم",
    flipCamera: "چرخش دوربین"
  },
  en: {
    sensorRole: "Tablet Sensor",
    connecting: "Connecting...",
    online: "Connected",
    offline: "Disconnected",
    deviceIdLabel: "Device ID:",
    fpsLabel: "Frame Rate:",
    framesSentLabel: "Frames Sent:",
    cameraErrorTitle: "Camera Access Error",
    cameraErrorDesc: "Camera startup did not finish. The specific reason will appear here.",
    retryCameraBtn: "Retry",
    selectCamera: "Select Camera:",
    defaultCamera: "Default Camera (Back)",
    pauseStream: "Pause Stream",
    resumeStream: "Resume Stream",
    flipCamera: "Flip Camera"
  }
};

let currentLang = localStorage.getItem("smartshelf_lang") || "fa";
let deviceId = localStorage.getItem("smartshelf_device_id");

if (!deviceId) {
  deviceId = "camera_tab_" + Math.random().toString(36).substring(2, 8);
  localStorage.setItem("smartshelf_device_id", deviceId);
}

let socket = null;
let currentStream = null;
let captureInterval = null;
let heartbeatInterval = null;
let isStreamingActive = true;
let framesSent = 0;
let lastFpsTime = Date.now();
let framesInSecond = 0;
let currentFacingMode = "environment"; // default to back camera

const TARGET_WIDTH = 640;
const FRAME_INTERVAL_MS = 200; // ~5 FPS

// Offscreen canvas for frame downscaling & compression
const canvas = document.createElement("canvas");
const ctx = canvas.getContext("2d", { willReadFrequently: false });

function applyLanguage(lang) {
  currentLang = lang;
  localStorage.setItem("smartshelf_lang", lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "fa" ? "rtl" : "ltr";

  const btn = document.getElementById("langToggleBtn");
  if (btn) btn.textContent = lang === "fa" ? "EN" : "فارسی";

  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (I18N[lang] && I18N[lang][key]) {
      el.textContent = I18N[lang][key];
    }
  });

  updateStreamButtonText();
  if(lastCameraError)showCameraError(lastCameraError.error,lastCameraError.phase);
}

function updateWsBadge(status) {
  const badge = document.getElementById("wsStatusBadge");
  const text = document.getElementById("wsStatusText");
  if (!badge || !text) return;

  badge.className = "status-badge " + status;
  if (status === "online") {
    text.textContent = I18N[currentLang].online;
  } else if (status === "offline") {
    text.textContent = I18N[currentLang].offline;
  } else {
    text.textContent = I18N[currentLang].connecting;
  }
}

function updateStreamButtonText() {
  const textEl = document.getElementById("toggleStreamText");
  if (!textEl) return;
  textEl.textContent = isStreamingActive
    ? I18N[currentLang].pauseStream
    : I18N[currentLang].resumeStream;
}

// ---------------------------------------------------------------------------
// Camera Hardware Access
// ---------------------------------------------------------------------------

let cameraInitEpoch = 0;
let lastCameraError = null;

function showCameraError(error, phase='media') {
  lastCameraError={error,phase};
  const english=currentLang==='en',name=error?.name||'Error';
  let title=english?'Camera could not start':'دوربین راه‌اندازی نشد';
  let description;
  if(phase==='play') {
    title=english?'Tap to start the preview':'برای شروع نمایش دوربین، دکمه را بزنید';
    description=english?'Camera access was granted, but video playback did not start. Tap Retry to start the preview.':'مجوز دوربین دریافت شده، اما پخش تصویر شروع نشده است. «تلاش مجدد» را بزنید تا نمایش تصویر با لمس شما آغاز شود.';
  } else if(name==='NotReadableError'||name==='TrackStartError'||name==='CameraEnded') {
    description=english?'The camera is busy or was stopped by the device. Close other camera apps and SmartShelf camera tabs, then retry.':'دوربین در برنامه یا صفحهٔ دیگری در حال استفاده است، یا دستگاه آن را متوقف کرده است. برنامهٔ دوربین و صفحه‌های دیگرِ آزمایشگاه بطری یا فروشگاه را ببندید و دوباره تلاش کنید.';
  } else if(name==='NotAllowedError'||name==='PermissionDeniedError'||name==='SecurityError') {
    description=english?'The browser or operating system blocked camera access. Open this HTTPS page directly in Chrome and check both site permission and the device Camera privacy setting.':'مرورگر یا سیستم‌عامل دسترسی را مسدود کرده است. این صفحهٔ HTTPS را مستقیم در Chrome باز کنید و علاوه بر مجوز سایت، دسترسی دوربینِ خود Chrome و کلید حریم خصوصی دوربینِ تبلت را بررسی کنید.';
  } else if(name==='NotFoundError'||name==='DevicesNotFoundError') {
    description=english?'No usable camera was found. Select another camera and retry.':'دوربین قابل استفاده پیدا نشد. دوربین دیگری را انتخاب و دوباره تلاش کنید.';
  } else if(name==='InsecureContext') {
    description=english?'Open https://shelf-ir.vercel.app/camera/ directly in the browser.':'صفحه را مستقیم با این آدرس باز کنید: https://shelf-ir.vercel.app/camera/';
  } else if(name==='CameraUnsupported') {
    description=english?'This browser does not expose camera access. Open the link in an up-to-date standalone browser.':'این مرورگر رابط دسترسی به دوربین را ارائه نمی‌کند. لینک را مستقیم در مرورگر به‌روز باز کنید؛ از مرورگر داخلی پیام‌رسان استفاده نکنید.';
  } else if(name==='OverconstrainedError'||name==='ConstraintNotSatisfiedError') {
    description=english?'The selected camera settings are unavailable. Try the default camera.':'تنظیمات دوربین انتخاب‌شده در دسترس نیست؛ دوربین پیش‌فرض را انتخاب کنید.';
  } else if(name==='AbortError'||name==='InvalidStateError') {
    description=english?'The camera request was interrupted. Keep this page in the foreground and retry.':'درخواست دوربین متوقف شد. این صفحه را باز و در پیش‌زمینه نگه دارید و دوباره تلاش کنید.';
  } else {
    description=english?'Camera startup failed. Retry and share the error code below if it continues.':'خطایی هنگام راه‌اندازی صفحه رخ داد. دوباره تلاش کنید و اگر ادامه داشت، کد خطای زیر را بفرستید.';
  }
  const titleNode=document.getElementById('cameraErrorTitle'),textNode=document.getElementById('cameraErrorDesc'),codeNode=document.getElementById('cameraErrorCode');
  if(titleNode)titleNode.textContent=title;
  if(textNode)textNode.textContent=description;
  if(codeNode)codeNode.textContent=name;
  const box=document.getElementById('cameraErrorBox');if(box)box.style.display='flex';
}

async function initCamera(exactDeviceId=null,reuseStream=false) {
  const epoch=++cameraInitEpoch,video=document.getElementById('cameraVideo'),errorBox=document.getElementById('cameraErrorBox');
  let phase='media',acquired=null;
  try {
    if(window.isSecureContext===false)throw Object.assign(new Error('HTTPS required'),{name:'InsecureContext'});
    if(!navigator.mediaDevices?.getUserMedia)throw Object.assign(new Error('Camera API unavailable'),{name:'CameraUnsupported'});
    const reusable=reuseStream&&currentStream?.getVideoTracks().some(track=>track.readyState==='live');
    if(reusable)acquired=currentStream;
    else {
      const previous=currentStream;currentStream=null;
      previous?.getTracks().forEach(track=>track.stop());
      const constraints={audio:false,video:{width:{ideal:1280},height:{ideal:720},frameRate:{ideal:30,max:30}}};
      if(exactDeviceId)constraints.video.deviceId={exact:exactDeviceId};else constraints.video.facingMode={ideal:currentFacingMode};
      try {acquired=await navigator.mediaDevices.getUserMedia(constraints);}
      catch(error){
        if(!['OverconstrainedError','ConstraintNotSatisfiedError','NotFoundError','DevicesNotFoundError'].includes(error.name)||epoch!==cameraInitEpoch)throw error;
        acquired=await navigator.mediaDevices.getUserMedia({audio:false,video:true});
      }
    }
    if(epoch!==cameraInitEpoch||!cameraPageActive){acquired?.getTracks().forEach(track=>track.stop());return;}
    currentStream=acquired;video.srcObject=acquired;video.muted=true;video.playsInline=true;
    phase='play';await video.play();
    if(epoch!==cameraInitEpoch||!cameraPageActive)return;
    const track=acquired.getVideoTracks()[0];
    if(track)track.addEventListener('ended',()=>{
      if(currentStream!==acquired||!cameraPageActive)return;
      updateWsBadge('offline');showCameraError({name:'CameraEnded'});
    },{once:true});
    errorBox.style.display='none';lastCameraError=null;
    phase='capture';await populateCameraDevices();startFrameCapture();
    startTabletWebRTC();
  } catch(error) {
    if(epoch!==cameraInitEpoch||!cameraPageActive)return;
    // Playback failure can be retried with a user gesture using the same stream.
    if(phase!=='play'&&acquired&&currentStream===acquired){currentStream=null;acquired.getTracks().forEach(track=>track.stop());}
    showCameraError(error,phase);
  }
}

async function populateCameraDevices() {
  const select = document.getElementById("cameraSelect");
  if (!select) return;

  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter(d => d.kind === "videoinput");

    // Preserve selection
    const currentVal = select.value;
    select.innerHTML = `<option value="">${I18N[currentLang].defaultCamera}</option>`;

    videoDevices.forEach((dev, idx) => {
      const opt = document.createElement("option");
      opt.value = dev.deviceId;
      opt.textContent = dev.label || `Camera ${idx + 1}`;
      if (dev.deviceId === currentVal) opt.selected = true;
      select.appendChild(opt);
    });
  } catch (e) {
    console.warn("Could not list video devices:", e);
  }
}

// ---------------------------------------------------------------------------
// Frame Capture & Compression (Strictly in-memory, ~5 FPS)
// ---------------------------------------------------------------------------

let frameInFlight = false;
let frameUploadController = null;
let lastHttpAttempt = 0;
let awaitingFrameAck = false;
let pendingFrameSince = 0;

function cameraDetail(text) {
  const element = document.getElementById("cameraTransportDetail");
  if (element) element.textContent = text;
}
function confirmFrame() {
  framesSent++; framesInSecond++;
  const counter=document.getElementById("framesSentCounter"),fps=document.getElementById("fpsCounter");
  if(counter)counter.textContent=framesSent;
  const now=Date.now();
  if(now-lastFpsTime>=1000){if(fps)fps.textContent=`${Math.round(framesInSecond*1000/(now-lastFpsTime))} FPS`;framesInSecond=0;lastFpsTime=now;}
}
async function uploadCameraFrame(blob) {
  const token=localStorage.getItem("smartshelf_device_token");
  const epoch=cameraConnectionEpoch;
  if(!token)return;
  const controller=new AbortController();frameUploadController=controller;
  const deadline=setTimeout(()=>controller.abort(),10000);
  try {
    const url=window.SmartShelfApi.apiUrl(`/api/camera/frame?device_id=${encodeURIComponent(deviceId)}`);
    const response=await fetch(url,{method:"POST",headers:{Authorization:`Bearer ${token}`,"Content-Type":"image/jpeg"},body:blob,signal:controller.signal});
    if(!cameraPageActive||epoch!==cameraConnectionEpoch||localStorage.getItem("smartshelf_device_token")!==token)return;
    if(response.status===401){localStorage.removeItem("smartshelf_device_token");showPairingModal();updateWsBadge("offline");cameraDetail("جفت‌سازی قبلی معتبر نیست؛ از پنل یک کد تازه بگیرید.");return;}
    if(!response.ok)throw new Error(response.status===404?"برای ارسال HTTPS، به‌روزرسانی اتصال دوربین را روی Windows نصب کنید.":`ارسال تصویر ناموفق بود (${response.status})؛ دوباره تلاش می‌شود.`);
    const data=await response.json();if(data.type!=="frame_received")throw new Error("سرور دریافت فریم را تأیید نکرد.");
    confirmFrame();updateWsBadge("online");localStorage.setItem("smartshelf_tablet_connected","true");cameraDetail("تصویر با HTTPS به سرور می‌رسد؛ اتصال جایگزین فعال است.");
  } catch(error){if(cameraPageActive&&epoch===cameraConnectionEpoch){updateWsBadge("offline");localStorage.setItem("smartshelf_tablet_connected","false");cameraDetail(error.name==="AbortError"?"پاسخ سرور دیر رسید؛ ارسال تصویر دوباره امتحان می‌شود.":error.message);}}
  finally{clearTimeout(deadline);if(frameUploadController===controller)frameUploadController=null;}
}
function startFrameCapture() {
  if(captureInterval)clearInterval(captureInterval);
  const video=document.getElementById("cameraVideo");
  captureInterval=setInterval(()=>{
    if(!cameraPageActive||!isStreamingActive||!currentStream||video.readyState<2||frameInFlight)return;
    const usingHttp=cameraTransport==="https";
    if(usingHttp){if(Date.now()-lastHttpAttempt<350||!localStorage.getItem("smartshelf_device_token"))return;}
    else if(!socket||socket.readyState!==WebSocket.OPEN||!cameraAuthConfirmed||awaitingFrameAck||socket.bufferedAmount>256*1024)return;
    const width=video.videoWidth,height=video.videoHeight;if(!width||!height)return;
    canvas.width=TARGET_WIDTH;canvas.height=Math.round(height*TARGET_WIDTH/width);ctx.drawImage(video,0,0,canvas.width,canvas.height);
    frameInFlight=true;
    canvas.toBlob(async blob=>{
      try {
        if(!blob||!cameraPageActive||!isStreamingActive)return;
        if(cameraTransport==="https"){lastHttpAttempt=Date.now();await uploadCameraFrame(blob);}
        else if(socket&&socket.readyState===WebSocket.OPEN&&cameraAuthConfirmed){awaitingFrameAck=serverFrameAck;pendingFrameSince=Date.now();socket.send(blob);if(!serverFrameAck)confirmFrame();}
      }catch(error){useHttpsTransport("ارتباط WSS قطع شد؛ ارسال از HTTPS ادامه پیدا می‌کند.");}
      finally{frameInFlight=false;}
    },"image/jpeg",.65);
  },FRAME_INTERVAL_MS);
}

// ---------------------------------------------------------------------------
// Camera Pairing & WebRTC Peer Stream
// ---------------------------------------------------------------------------

let pairedCode = localStorage.getItem("smartshelf_paired_code") || "";
let tabletRtcPublisher = null;
function setFrameTransmission(enabled) {
  if(enabled&&(!cameraPageActive||!currentStream?.getVideoTracks().some(track=>track.readyState==='live')))throw new Error('دوربین تبلت آماده نیست؛ صفحهٔ دوربین را بررسی کنید.');
  isStreamingActive=enabled;
  updateStreamButtonText();
  if(enabled){if(!captureInterval)startFrameCapture();if(cameraTransport!=='https')connectCameraWs();}
  else {frameUploadController?.abort();framesInSecond=0;const fps=document.getElementById('fpsCounter');if(fps)fps.textContent='0 FPS';}
  cameraDetail(enabled?'ارسال تصویر هوش مصنوعی فعال شد؛ منتظر تأیید فریم سرور…':'ارسال تصویر هوش مصنوعی متوقف شد؛ ویدیوی WebRTC همچنان فعال است.');
  return {enabled:isStreamingActive};
}
function startTabletWebRTC() {
  if(!window.SmartShelfRTC)return;
  if(!tabletRtcPublisher)tabletRtcPublisher=new window.SmartShelfRTC.Publisher({deviceId,getToken:()=>localStorage.getItem('smartshelf_device_token'),onControl:setFrameTransmission,onState:(_state,text)=>{const el=document.getElementById('rtcStatus');if(el)el.textContent=text;}});
  tabletRtcPublisher.setStream(currentStream).catch(()=>{});
  tabletRtcPublisher.setEnabled(true);
  tabletRtcPublisher.start();
}

function showPairingModal() {
  const modal = document.getElementById("pairingModal");
  if (modal) modal.style.display = "flex";
}

function hidePairingModal() {
  const modal = document.getElementById("pairingModal");
  if (modal) modal.style.display = "none";
}

async function submitPairingCode() {
  const input = document.getElementById("pairingCodeInput");
  const errEl = document.getElementById("pairingErrorMsg");
  const rawCode = input?.value || "";
  const code = window.SmartShelfFormat.normalizePairingCode(rawCode);
  if (!/^[0-9]{6}$/.test(code)) {
    if (errEl) {
      errEl.textContent = "کد جفت‌سازی باید دقیقاً ۶ رقم باشد.";
      errEl.style.display = "block";
    }
    return;
  }
  if (input) input.value = code;

  if (errEl) { errEl.style.display = "none"; errEl.textContent = ""; }
  updateWsBadge("connecting");
  try {
    const pairUrl = window.SmartShelfApi
      ? window.SmartShelfApi.apiUrl("/api/camera/pair")
      : "/api/camera/pair";
    const res = await fetch(pairUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, pairing_code: code, device_id: deviceId })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.device_token) {
      throw new Error(data.detail || `جفت‌سازی ناموفق بود (HTTP ${res.status})`);
    }

    pairedCode = code;
    localStorage.setItem("smartshelf_paired_code", code);
    localStorage.setItem("smartshelf_device_token", data.device_token);
    tabletRtcPublisher?.stop();
    startTabletWebRTC();
    localStorage.setItem("smartshelf_tablet_connected", "false");
    hidePairingModal();
    resetCameraConnection();
    connectCameraWs();
  } catch (err) {
    localStorage.removeItem("smartshelf_device_token");
    localStorage.setItem("smartshelf_tablet_connected", "false");
    if (errEl) {
      errEl.textContent = err.message || "بک‌اند در دسترس نیست؛ آدرس سرور را بررسی کنید.";
      errEl.style.display = "block";
    }
    updateWsBadge("offline");
  }
}

let cameraReconnectTimer = null;
let cameraAuthTimer = null;
let cameraConnectTimer = null;
let cameraAuthConfirmed = false;
let cameraReconnectDelay = 1000;
let cameraTransport = "wss";
let cameraPageActive = true;
let serverFrameAck = false;
let lastServerMessage = 0;
let cameraConnectionEpoch = 0;

function resetCameraConnection() {
  cameraConnectionEpoch++;frameUploadController?.abort();
  clearTimeout(cameraAuthTimer);clearTimeout(cameraConnectTimer);clearTimeout(cameraReconnectTimer);clearInterval(heartbeatInterval);
  cameraAuthTimer=cameraConnectTimer=cameraReconnectTimer=heartbeatInterval=null;
  const previous=socket;socket=null;
  if(previous)try{previous.close(1000,"reconnect");}catch{}
  cameraAuthConfirmed=false;awaitingFrameAck=false;cameraTransport="wss";
}
function useHttpsTransport(reason) {
  if(!cameraPageActive)return;
  resetCameraConnection();cameraTransport="https";
  updateWsBadge("connecting");cameraDetail(reason||"WSS پاسخ نداد؛ در حال ارسال تصویر از HTTPS…");
}
function connectCameraWs() {
  const deviceToken=localStorage.getItem("smartshelf_device_token");
  if(!deviceToken||deviceToken.length<32){localStorage.removeItem("smartshelf_device_token");localStorage.setItem("smartshelf_tablet_connected","false");showPairingModal();updateWsBadge("offline");cameraDetail("ابتدا کد شش‌رقمی جفت‌سازی دوربین را از پنل وارد کنید.");return;}
  if(!cameraPageActive||cameraTransport==="https"||(socket&&(socket.readyState===WebSocket.OPEN||socket.readyState===WebSocket.CONNECTING)))return;
  updateWsBadge("connecting");cameraDetail("در حال برقراری ارتباط امن با سرور…");
  try {
    const ws=new WebSocket(window.SmartShelfApi.wsUrl(`/ws/camera?device_id=${encodeURIComponent(deviceId)}`));socket=ws;ws.binaryType="blob";
    cameraConnectTimer=setTimeout(()=>{if(socket===ws&&!cameraAuthConfirmed)useHttpsTransport();},8000);
    ws.onopen=()=>{
      if(socket!==ws)return;
      clearTimeout(cameraConnectTimer);cameraConnectTimer=null;
      cameraAuthConfirmed=false;localStorage.setItem("smartshelf_tablet_connected","false");
      ws.send(JSON.stringify({type:"auth",device_token:deviceToken,frame_ack:true}));
      cameraAuthTimer=setTimeout(()=>{if(socket===ws&&!cameraAuthConfirmed)useHttpsTransport("تأیید WSS دیر رسید؛ ارسال از HTTPS امتحان می‌شود.");},8000);
    };
    ws.onmessage=event=>{
      if(socket!==ws)return;lastServerMessage=Date.now();
      if(event.data==="pong")return;
      try {
        const data=JSON.parse(event.data);
        if(data.type==="connected"){
          clearTimeout(cameraAuthTimer);cameraAuthTimer=null;cameraAuthConfirmed=true;serverFrameAck=data.frame_ack===true;awaitingFrameAck=false;
          hidePairingModal();cameraDetail("ارتباط با سرور برقرار است؛ منتظر اولین فریم دوربین…");
          if(!serverFrameAck){updateWsBadge("online");localStorage.setItem("smartshelf_tablet_connected","true");}
          clearInterval(heartbeatInterval);
          heartbeatInterval=setInterval(()=>{if(socket!==ws)return;if(Date.now()-lastServerMessage>12000||(awaitingFrameAck&&Date.now()-pendingFrameSince>10000)){useHttpsTransport("تأیید دریافت تصویر نرسید؛ ارسال HTTPS فعال شد.");return;}if(ws.readyState===WebSocket.OPEN)ws.send("ping");},5000);
        } else if(data.type==="frame_received"){
          awaitingFrameAck=false;confirmFrame();updateWsBadge("online");localStorage.setItem("smartshelf_tablet_connected","true");cameraDetail("تصویر زنده با WSS به سرور می‌رسد.");
        } else if(data.type==="vision_control" && typeof data.enabled==="boolean"){
          // The server controls AI JPEG upload even if WebRTC preview is down.
          try{
            setFrameTransmission(data.enabled);
            if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:"vision_control_ack",enabled:isStreamingActive}));
          }catch(error){
            if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:"vision_control_ack",enabled:false,error:String(error.message||error)}));
          }
        }
      }catch{}
    };
    ws.onclose=event=>{
      if(socket!==ws||!cameraPageActive)return;
      socket=null;clearTimeout(cameraAuthTimer);clearTimeout(cameraConnectTimer);clearInterval(heartbeatInterval);cameraAuthConfirmed=false;awaitingFrameAck=false;
      localStorage.setItem("smartshelf_tablet_connected","false");
      if(event.code===1008){localStorage.removeItem("smartshelf_device_token");showPairingModal();updateWsBadge("offline");cameraDetail("جفت‌سازی دوربین منقضی شده است؛ یک کد تازه از پنل بگیرید.");}
      else useHttpsTransport("ارتباط WSS قطع شد؛ ارسال تصویر از HTTPS امتحان می‌شود.");
    };
    ws.onerror=()=>{if(socket===ws)useHttpsTransport("ارتباط WSS برقرار نشد؛ ارسال تصویر از HTTPS امتحان می‌شود.");};
  }catch(error){useHttpsTransport(error.message);}
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("deviceIdText").textContent = deviceId;
  applyLanguage(currentLang);

  const urlParams = new URLSearchParams(window.location.search);
  const autoCode = urlParams.get("code") || urlParams.get("pairing_code");
  if (autoCode) {
    const input = document.getElementById("pairingCodeInput");
    if (input) input.value = autoCode.trim();
    setTimeout(submitPairingCode, 200);
  }

  // Wake Lock API to prevent screen sleep during kiosk mode
  let wakeLock = null;
  async function requestWakeLock() {
    try {
      if ("wakeLock" in navigator) {
        wakeLock = await navigator.wakeLock.request("screen");
        wakeLock.addEventListener("release", () => { wakeLock = null; });
      }
    } catch (e) {}
  }
  document.addEventListener("visibilitychange", () => {
    if (wakeLock !== null && document.visibilityState === "visible") {
      requestWakeLock();
    }
  });
  requestWakeLock();

  window.addEventListener("pageshow",event=>{if(event.persisted){cameraPageActive=true;resetCameraConnection();initCamera();connectCameraWs();}});

  // Fullscreen toggle button
  document.getElementById("fullscreenBtn")?.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  });

  // Language button
  document.getElementById("langToggleBtn")?.addEventListener("click", () => {
    applyLanguage(currentLang === "fa" ? "en" : "fa");
  });

  // Config Server button
  document.getElementById("configServerBtn")?.addEventListener("click", () => {
    if (window.SmartShelfApi) {
      window.SmartShelfApi.showServerConfigModal();
    }
  });

  // Camera switch selector
  document.getElementById("cameraSelect")?.addEventListener("change", (e) => {
    initCamera(e.target.value || null);
  });

  // Flip front/back camera
  document.getElementById("flipCameraBtn")?.addEventListener("click", () => {
    currentFacingMode = currentFacingMode === "environment" ? "user" : "environment";
    initCamera(null);
  });

  // Retry camera button
  document.getElementById("retryCameraBtn")?.addEventListener("click", () => {
    initCamera(null,true);
  });

  // Camera pairing submit button
  document.getElementById("submitPairingBtn")?.addEventListener("click", submitPairingCode);
  document.getElementById("pairingCodeInput")?.addEventListener("keypress", (e) => {
    if (e.key === "Enter") submitPairingCode();
  });

  // Toggle stream on/off
  document.getElementById("toggleStreamBtn")?.addEventListener("click", () => {
    try{setFrameTransmission(!isStreamingActive);}catch(error){cameraDetail(error.message);}
  });

  // No client-side simulated pick/return events: all shelf decisions are made by the backend.
  document.getElementById("camPickBtn")?.remove();
  document.getElementById("camReturnBtn")?.remove();

  initCamera();
  connectCameraWs();
  document.getElementById("retryTransportBtn")?.addEventListener("click",()=>{resetCameraConnection();connectCameraWs();});

  window.addEventListener("pagehide", () => {
    cameraPageActive=false;frameUploadController?.abort();
    tabletRtcPublisher?.stop();
    clearTimeout(cameraConnectTimer);
    if (captureInterval) clearInterval(captureInterval);
    if (heartbeatInterval) clearInterval(heartbeatInterval);
    if (cameraReconnectTimer) clearTimeout(cameraReconnectTimer);
    if (cameraAuthTimer) clearTimeout(cameraAuthTimer);
    if (socket) {
      try { socket.close(1000, "pagehide"); } catch (e) {}
      socket = null;
    }
    if (currentStream) {
      currentStream.getTracks().forEach(track => track.stop());
      currentStream = null;
    }
  });

});

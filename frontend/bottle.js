/* Full-scene detector and explicit sample review; no cart or inventory writes. */
'use strict';
const $ = id => document.getElementById(id);
const canvas = $('canvas'), ctx = canvas.getContext('2d');
let token = sessionStorage.getItem('smartshelf_admin_token') || '';
let image = null, frameData = null, boxes = [], detections = [], stream = null, live = false, pointerStart = null;
let busy = false, imageVersion = 0, liveEpoch = 0;
let liveController = null;
const labels = ['هی‌جو هلو', 'بطری دیگر'];
function message(text) { $('message').textContent = text; }
function liveStatus(text) { $('liveStatus').textContent = text; }
async function request(path, options = {}) {
  let res;
  try { res = await fetch(SmartShelfApi.apiUrl(path), {...options, headers: {'Authorization': `Bearer ${token}`, ...(options.body ? {'Content-Type':'application/json'} : {}), ...options.headers}}); }
  catch(error) {
    if (error.name === 'AbortError') throw error;
    const failure = new Error('ارتباط با بک‌اند قطع است؛ اتصال اینترنت و روشن‌بودن سرور را بررسی کنید.');
    failure.retryable = true; throw failure;
  }
  if (res.status === 401) { token = ''; sessionStorage.removeItem('smartshelf_admin_token'); $('loginCard').hidden = false; stopLive(); throw new Error('برای ادامه وارد پنل شوید.'); }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const failure = new Error(res.status === 404 ? 'بک‌اند هنوز ابزار تشخیص جدید را ندارد؛ بستهٔ به‌روزرسانی Windows را نصب و بک‌اند را دوباره اجرا کنید.' : (typeof data.detail === 'string' ? data.detail : `درخواست ناموفق (${res.status})`));
    failure.retryable = [408,409,425,429,500,502,504].includes(res.status);
    throw failure;
  }
  return res;
}
async function refreshStatus() {
  const data = await (await request('/api/bottle/status')).json();
  $('modelStatus').textContent = data.ready ? `مدل فعال: ${data.model}` : (data.error || 'مدل آماده نیست');
  $('modelNote').textContent = data.mode === 'custom_product' ? 'مدل اختصاصی بارگذاری شده است؛ عملکرد در محیط جدید باید آزموده شود. خرید خودکار فعال نیست.' : 'مدل آمادهٔ عمومی بطری: نام برند و طعم هنوز تأیید نمی‌شود. برای آموزش هی‌جو از بخش ثبت نمونه استفاده کنید.';
  updateDataset(data.dataset);
}
function updateDataset(d) { $('datasetStatus').textContent = `${d.samples} عکس بررسی‌شده · ${d.environments.length} محیط · ${d.negative_images} عکس بدون بطری`; }
function draw(preview = null) {
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if (image) ctx.drawImage(image,0,0,canvas.width,canvas.height);
  [...detections.map(d => ({...d, title: d.class_name === 'heyjo_peach' ? 'تشخیص مدل: هی‌جو هلو' : d.class_name === 'other_bottle' ? 'تشخیص مدل: بطری دیگر' : 'تشخیص مدل: بطری؛ برند نامشخص', color:'#ffcf70'})), ...boxes.map(b => ({...b,title: `برچسب دستی: ${labels[b.class_id]}`,color:'#71edb6'})), ...(preview ? [{box:preview,title:'کادر دستی',color:'#90baff'}] : [])].forEach(b => {
    const [x1,y1,x2,y2] = b.box.map((v,i) => v * (i % 2 === 0 ? canvas.width : canvas.height));
    ctx.strokeStyle = b.color; ctx.lineWidth = Math.max(2,canvas.width/400); ctx.strokeRect(x1,y1,x2-x1,y2-y1);
    const fontSize=Math.max(16,Math.round(canvas.width/65));
    ctx.font = `${fontSize}px Dana, sans-serif`; ctx.textAlign='right';ctx.direction='rtl';
    const title = b.title + (b.confidence != null ? ` · امتیاز ${Math.round(b.confidence*100).toLocaleString('fa-IR')}٪` : '');
    const labelWidth=Math.min(canvas.width,ctx.measureText(title).width+16),right=Math.max(labelWidth,Math.min(canvas.width,x2)),top=Math.max(0,y1-fontSize-13);
    ctx.fillStyle='#09121de6';ctx.fillRect(right-labelWidth,top,labelWidth,fontSize+13);ctx.fillStyle=b.color;ctx.fillText(title,right-8,top+fontSize+2,Math.max(1,labelWidth-16));
  });
}
async function setImage(data, stillCurrent=()=>true) {
  const next = new Image(); await new Promise((resolve,reject) => { next.onload=resolve;next.onerror=reject;next.src=data; });
  if(!stillCurrent())return false;
  image=next; canvas.width=next.naturalWidth;canvas.height=next.naturalHeight;frameData=data;
  imageVersion++;boxes=[];detections=[];$('negative').checked=false;$('reviewed').checked=false;
  $('placeholder').hidden=true;$('detect').disabled=live;$('save').disabled=live;pointerStart=null;renderBoxes();draw();return true;
}
function renderBoxes() {
  $('boxes').replaceChildren();
  boxes.forEach((b,i) => { const li=document.createElement('li');li.textContent=`${i+1}. برچسب دستی: ${labels[b.class_id]}`; const btn=document.createElement('button');btn.textContent='حذف';btn.onclick=()=>{boxes.splice(i,1);$('reviewed').checked=false;renderBoxes();draw();};li.appendChild(btn);$('boxes').appendChild(li); });
}
function updateAnnotationMode() {
  pointerStart=null;const enabled=$('annotationMode').checked&&!live;
  canvas.classList.toggle('annotating',enabled);$('classId').disabled=!enabled;draw();
}
function stopLive(text='آزمایش زنده متوقف است.') {
  live=false;liveEpoch++;liveController?.abort();liveController=null;
  $('stop').hidden=true;$('live').disabled=false;$('liveSource').disabled=false;
  $('annotationMode').disabled=false;$('detect').disabled=!image;$('save').disabled=!image;
  liveStatus(text);updateAnnotationMode();
}
async function openCamera(epoch=null) {
  const video=$('video');
  if(!stream?.getVideoTracks().some(track=>track.readyState==='live')) {
    if(!navigator.mediaDevices?.getUserMedia)throw new Error('دوربین در دسترس نیست؛ صفحه را با HTTPS باز کنید و مجوز دوربین را بررسی کنید.');
    stream?.getTracks().forEach(track=>track.stop());
    const next=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
    if(epoch!==null&&(!live||epoch!==liveEpoch)){next.getTracks().forEach(track=>track.stop());return;}
    stream=next;video.srcObject=stream;
  }
  video.hidden=false;await video.play();$('snapshot').disabled=false;
}
function captureFrame() {
  const video=$('video');
  if(!stream?.getVideoTracks().some(track=>track.readyState==='live')||!video.videoWidth||video.readyState<2){const error=new Error('منتظر تصویر دوربین همین دستگاه هستیم؛ مجوز دوربین و بازبودن صفحه را بررسی کنید.');error.retryable=true;throw error;}
  const c=document.createElement('canvas'),scale=Math.min(1,1600/Math.max(video.videoWidth,video.videoHeight));
  c.width=Math.round(video.videoWidth*scale);c.height=Math.round(video.videoHeight*scale);c.getContext('2d').drawImage(video,0,0,c.width,c.height);
  return c.toDataURL('image/jpeg',.9);
}
async function detect(source='upload', epoch=null) {
  if (busy || (source==='upload' && !frameData)) return false;
  busy=true;const version=imageVersion,current=()=>epoch===null||(live&&epoch===liveEpoch);
  let timeout=null,controller=null;
  try {
    let frame=source==='local'?captureFrame():frameData;
    const payload={source:source==='tablet'?'tablet':'upload',threshold:Number($('threshold').value)};if(payload.source==='upload')payload.frame=frame;
    controller=new AbortController();if(epoch!==null)liveController=controller;
    let timedOut=false;timeout=setTimeout(()=>{timedOut=true;controller.abort();},20000);
    let data;
    try {data=await(await request('/api/bottle/detect',{method:'POST',body:JSON.stringify(payload),signal:controller.signal})).json();}
    catch(error){if(timedOut){const retry=new Error('پاسخ سرور دیر رسید؛ دوباره تلاش می‌کنیم.');retry.retryable=true;throw retry;}throw error;}
    if(!current())return false;
    if(source!=='upload'){
      frame=source==='tablet'?data.frame:frame;
      if(!frame)throw new Error('سرور تصویر آزمایش‌شده را برنگرداند؛ بک‌اند را بررسی کنید.');
      if(!await setImage(frame,current))return false;
    }else if(version!==imageVersion)return false;
    detections=data.detections;draw();
    $('result').textContent=`${data.bottle_count} بطری · ${data.elapsed_ms} میلی‌ثانیه پردازش · ${data.mode==='custom_product' ? `${data.target_count} تشخیص هی‌جو توسط مدل اختصاصی` : 'هویت برند نامشخص'}؛ ندیدن بطری اثبات خالی بودن جایگاه نیست.`;
    if(epoch!==null)liveStatus(source==='local'?'آزمایش زنده فعال است — دوربین همین دستگاه':'آزمایش زنده فعال است — تبلت متصل');
    message('');return true;
  } catch(e) {
    if(!current()||e.name==='AbortError')return false;
    if(epoch!==null&&e.retryable){
      detections=[];draw();$('result').textContent='نتیجهٔ زنده در دسترس نیست؛ تصویر قبلی ممکن است قدیمی باشد.';
      liveStatus('در انتظار تصویر یا اتصال سرور؛ تلاش مجدد خودکار…');
      message(e.message+(source==='tablet'?' صفحهٔ /camera/ باید روی تبلت باز و ارسال تصویر فعال باشد؛ یا «دوربین همین دستگاه» را انتخاب کنید.':''));
    }else{if(epoch!==null)stopLive('آزمایش متوقف شد؛ پیام زیر را بررسی کنید.');message(e.message);}
    return false;
  } finally { clearTimeout(timeout);if(liveController===controller)liveController=null;busy=false; }
}
async function startLive() {
  if(live)return;live=true;const epoch=++liveEpoch,source=$('liveSource').value;
  $('stop').hidden=false;$('live').disabled=true;$('liveSource').disabled=true;
  $('annotationMode').checked=false;$('annotationMode').disabled=true;$('detect').disabled=true;$('save').disabled=true;updateAnnotationMode();message('');
  liveStatus(source==='local'?'در حال بازکردن دوربین همین دستگاه…':'منتظر تصویر تبلت متصل…');
  try{
    if(source==='local')await openCamera(epoch);
    let failures=0;
    while(live&&epoch===liveEpoch){const ok=await detect(source,epoch);failures=ok?0:failures+1;if(live&&epoch===liveEpoch)await new Promise(resolve=>setTimeout(resolve,ok?500:Math.min(5000,1000*failures)));}
  }catch(error){if(live&&epoch===liveEpoch){stopLive('دوربین باز نشد.');message(error.name==='NotAllowedError'?'اجازهٔ دسترسی به دوربین داده نشده است؛ از تنظیمات مرورگر مجوز دوربین را فعال کنید.':error.message);}}
}
function canvasPoint(event) {const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))];}
canvas.addEventListener('pointerdown',event=>{if(!image||live||!$('annotationMode').checked)return;event.preventDefault();pointerStart=canvasPoint(event);canvas.setPointerCapture(event.pointerId);});
canvas.addEventListener('pointermove',event=>{if(!pointerStart)return;const [x,y]=canvasPoint(event);draw([Math.min(x,pointerStart[0]),Math.min(y,pointerStart[1]),Math.max(x,pointerStart[0]),Math.max(y,pointerStart[1])]);});
canvas.addEventListener('pointerup',event=>{if(!pointerStart)return;const [x,y]=canvasPoint(event),[sx,sy]=pointerStart;pointerStart=null;if(Math.abs(x-sx)>.005&&Math.abs(y-sy)>.005){boxes.push({class_id:Number($('classId').value),box:[Math.min(x,sx),Math.min(y,sy),Math.max(x,sx),Math.max(y,sy)]});$('negative').checked=false;$('reviewed').checked=false;renderBoxes();}draw();});
canvas.addEventListener('pointercancel',()=>{pointerStart=null;draw();});
$('clearBoxes').onclick=()=>{boxes=[];$('reviewed').checked=false;renderBoxes();draw();};
$('photo').onchange=async()=>{try{stopLive();const file=$('photo').files[0];if(!file)return;if(file.size>20*1024*1024)throw new Error('عکس باید کوچک‌تر از ۲۰ مگابایت باشد.');const bitmap=await createImageBitmap(file);const c=document.createElement('canvas');const scale=Math.min(1,1600/Math.max(bitmap.width,bitmap.height));c.width=Math.round(bitmap.width*scale);c.height=Math.round(bitmap.height*scale);c.getContext('2d').drawImage(bitmap,0,0,c.width,c.height);bitmap.close();await setImage(c.toDataURL('image/jpeg',.94));message('');}catch(e){message(e.message);}};
$('camera').onclick=()=>{if(live)stopLive();$('liveSource').value='local';return startLive();};
$('snapshot').onclick=async()=>{stopLive();try{await setImage(captureFrame());message('عکس گرفته شد. برای تشخیص، «تشخیص این عکس» را بزنید.');}catch(e){message(e.message);}};
$('detect').onclick=()=>detect();
$('live').onclick=startLive;
$('stop').onclick=()=>{
  stopLive();
  stream?.getTracks().forEach(track=>track.stop());
  stream=null;
  $('video').srcObject=null;
  $('video').hidden=true;
  $('snapshot').disabled=true;
};
$('annotationMode').onchange=updateAnnotationMode;
$('liveSource').onchange=()=>{$('liveSourceHint').textContent=$('liveSource').value==='local'?'دوربین همین مرورگر استفاده می‌شود؛ جفت‌کردن تبلت لازم نیست.':'صفحهٔ /camera/ باید روی تبلت باز، جفت‌شده و در حال ارسال تصویر باشد. با همین گزینه دوربین این صفحه باز نمی‌شود.';};
$('threshold').oninput=()=>{$('thresholdValue').textContent=Number($('threshold').value).toLocaleString('fa-IR');};
$('save').onclick=async()=>{try{if(live)throw new Error('ابتدا آزمایش زنده را متوقف کنید، سپس کادرها را بررسی کنید.');if(!$('environment').value.trim())throw new Error('نام محیط را وارد کنید.');if(!$('reviewed').checked)throw new Error('پس از بررسی کادرها، تأیید را علامت بزنید.');if(!boxes.length&&!$('negative').checked)throw new Error('کادر بطری را بکشید یا عکس بدون بطری را صریحاً مشخص کنید.');if(boxes.length&&$('negative').checked)throw new Error('عکس دارای کادر نمی‌تواند بدون بطری باشد.');const d=await(await request('/api/bottle/samples',{method:'POST',body:JSON.stringify({frame:frameData,environment:$('environment').value.trim(),boxes,reviewed:true,negative:$('negative').checked})})).json();updateDataset(d.dataset);$('reviewed').checked=false;message('نمونه ثبت شد؛ برای زاویه یا محیط بعدی عکس متفاوتی بگیرید.');}catch(e){message(e.message);}};
$('export').onclick=async()=>{try{const res=await request('/api/bottle/dataset.zip'),url=URL.createObjectURL(await res.blob()),a=document.createElement('a');a.href=url;a.download='SmartShelf-bottle-dataset.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}catch(e){message(e.message);}};
$('loginForm').onsubmit=async event=>{event.preventDefault();try{const pin=SmartShelfFormat.normalizeDigits($('pin').value.trim());const res=await fetch(SmartShelfApi.apiUrl('/api/admin/login'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin})});const d=await res.json();if(!res.ok||!d.token)throw new Error(typeof d.detail==='string'?d.detail:'ورود ناموفق بود.');token=d.token;sessionStorage.setItem('smartshelf_admin_token',token);$('pin').value='';$('loginCard').hidden=true;message('');await refreshStatus();}catch(e){message(e.message);}};
window.addEventListener('pagehide',()=>{stopLive();stream?.getTracks().forEach(t=>t.stop());});
updateAnnotationMode();
if(token)refreshStatus().catch(e=>message(e.message));else{$('loginCard').hidden=false;$('modelStatus').textContent='برای بررسی مدل وارد شوید.';}

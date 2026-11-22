/* Live university store: every cart/stock decision belongs to the server. */
'use strict';
const $=id=>document.getElementById(id), canvas=$('canvas'), ctx=canvas.getContext('2d');
let token=sessionStorage.getItem('smartshelf_admin_token')||'',state=null,products=[];
let socket=null,reconnect=null,qrTimer=null,freshTimer=null,qrLoading=false,lastEntryKey=null;
let stream=null,preview=null,roi=[0,0,1,1],drag=null,working=false,loopEpoch=0,sequence=0;
let lastShopUpdate=0,controller=null,tabletViewer=null,controlBusy=false,framesConfirmed=false,scenarioBusy=false;
let previewAnimation=null,lastPreviewPaint=0;
const streamId=crypto.randomUUID(),fa=n=>Number(n||0).toLocaleString('fa-IR');
function notice(text){$('message').textContent=text;}
async function api(path,options={}){
  const response=await fetch(SmartShelfApi.apiUrl(path),{cache:'no-store',...options,headers:{Authorization:`Bearer ${token}`,...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});
  if(response.status===401){token='';sessionStorage.removeItem('smartshelf_admin_token');$('loginCard').hidden=false;stopFrames();stopVideoPreview();socket?.close();throw new Error('دوباره وارد پنل شوید.');}
  if(!response.ok){const d=await response.json().catch(()=>({}));throw new Error(response.status===404?'بک‌اند این نسخه را ندارد؛ بستهٔ به‌روزرسانی سناریو را روی Windows نصب و بک‌اند را دوباره اجرا کنید.':typeof d.detail==='string'?d.detail:`درخواست ناموفق (${response.status})`);}
  return response.json();
}
function render(shop){
  state=shop;lastShopUpdate=Date.now();
  $('stock').textContent=shop.stock_quantity===null?'نامشخص':fa(shop.stock_quantity);
  $('productName').textContent=shop.product_name||'محصول تعیین نشده';
  $('session').textContent=shop.session_id?`#${fa(shop.session_id)}`:'بدون مشتری';
  $('quantity').textContent=fa(shop.cart?.total_quantity||0);
  $('total').textContent=fa(shop.cart?.grand_total||0)+' تومان';
  const states={PRESENT:'بطری در جایگاه است',ABSENT:'جایگاه خالی است',UNKNOWN:'در انتظار تثبیت تصویر',TRANSITION:'در حال بررسی تغییر'};
  $('slotState').textContent=states[shop.state]||shop.state;
  $('status').textContent=shop.needs_review?'تغییر در زمان قطع تصویر رخ داده است؛ سبد خودکار تغییر نکرد. سشن را بررسی و پایان دهید و سناریو را دوباره تنظیم کنید.':shop.enabled?'سناریوی دانشگاهی فعال است؛ تغییرات پس از تثبیت چند فریم ثبت می‌شوند.':'سناریو متوقف است؛ برای شروع، محصول و جایگاه را مشخص کنید.';
  // A paused scenario can be resumed with the same shelf even with an active customer.
  $('enable').disabled=scenarioBusy||Boolean(shop.session_id&&shop.enabled);
  $('disable').disabled=scenarioBusy||!shop.enabled;
  $('cameraSource').disabled=shop.enabled||scenarioBusy;
  if(shop.enabled){$('cameraSource').value=shop.camera_source;roi=shop.roi;}
  $('cart').replaceChildren();
  for(const item of shop.cart?.items||[]){const p=document.createElement('p');p.textContent=`${item.product_name} × ${fa(item.quantity)} — ${fa(item.line_total)} تومان`;$('cart').appendChild(p);}
  if(!shop.cart?.items?.length)$('cart').textContent='سبد خالی است.';
  const key=`${shop.enabled}:${shop.session_id||''}`;
  if(key!==lastEntryKey){lastEntryKey=key;refreshEntry().catch(e=>notice(e.message));}
  updateFrameButtons();draw();
}
async function loadStatus(initial=false){
  const d=await api('/api/shop/status');products=d.products;
  if(initial){for(const [id,items] of [['product',d.products],['zone',d.zones]]){$(id).replaceChildren();for(const item of items){const option=document.createElement('option');option.value=String(item.id);option.textContent=item.name;$(id).appendChild(option);}}
    if(d.shop.product_id)$('product').value=String(d.shop.product_id);
    if(d.shop.zone_id)$('zone').value=String(d.shop.zone_id);
    $('price').value=String(products.find(p=>p.id===Number($('product').value))?.unit_price||0);
    $('cameraSource').value=d.shop.camera_source;roi=d.shop.roi;$('roiConfirmed').checked=d.shop.enabled;
  }
  render(d.shop);
}
async function refreshEntry(){
  clearTimeout(qrTimer);qrTimer=null;
  if(qrLoading)return;
  $('qr').replaceChildren();$('entryCode').value='';
  if(!state?.enabled){$('entryState').textContent='ابتدا سناریو را فعال کنید.';return;}
  if(state.session_id){$('entryState').textContent='یک مشتری فعال است؛ ورود بعدی پس از پایان این سشن باز می‌شود.';return;}
  qrLoading=true;
  try{
    const d=await api('/api/admin/token',{method:'POST'});
    if(!state?.enabled||state.session_id)return;
    if(d.active_session){$('entryState').textContent='فروشگاه یک مشتری فعال دارد.';return;}
    const entryUrl=new URL('/enter/',window.location.origin);entryUrl.searchParams.set('token',d.token);
    $('entryCode').value=d.token;$('entryLink').href=entryUrl.href;
    $('entryState').textContent='QR را با گوشی مشتری اسکن کنید؛ کد نیز تا زمان انقضا قابل ورود است.';
    new QRCode($('qr'),{text:entryUrl.href,width:180,height:180});
    qrTimer=setTimeout(()=>refreshEntry().catch(e=>notice(e.message)),Math.max(1000,(d.expires_in-2)*1000));
  }finally{qrLoading=false;}
}
function connect(){
  if(!token||socket?.readyState===WebSocket.OPEN||socket?.readyState===WebSocket.CONNECTING)return;
  socket=new WebSocket(SmartShelfApi.wsUrl('/ws/admin'));
  socket.onopen=()=>socket.send(JSON.stringify({type:'AUTH',token}));
  socket.onmessage=event=>{try{
    const msg=JSON.parse(event.data);
    if(msg.type==='AUTH_OK'){$('connection').textContent='ارتباط زنده برقرار است';loadStatus().catch(e=>notice(e.message));}
    if(msg.type==='SHOP_STATE')render(msg.shop);
    if(['CUSTOMER_ENTERED','SESSION_CLOSED','CART_UPDATED'].includes(msg.type))loadStatus().catch(e=>notice(e.message));
    if(msg.type==='EVENT_CREATED'&&['STOCK_SYNC','PRODUCT_PICKED','PRODUCT_RETURNED'].includes(msg.event?.type)){
      const li=document.createElement('li'),names={STOCK_SYNC:'موجودی اولیه مشخص شد',PRODUCT_PICKED:'برداشت بطری',PRODUCT_RETURNED:'برگشت بطری'};
      li.textContent=names[msg.event.type]+(msg.event.status==='PROCESSED'?' — سبد به‌روز شد':' — ثبت موجودی');$('events').prepend(li);while($('events').children.length>10)$('events').lastChild.remove();
    }
  }catch{}};
  socket.onclose=()=>{$('connection').textContent='ارتباط زنده قطع است؛ در حال اتصال مجدد…';if(token&&!reconnect)reconnect=setTimeout(()=>{reconnect=null;connect();},2000);};
  socket.onerror=()=>socket.close();
}
function draw(){
  const video=$('video');
  const live=video.srcObject&&video.readyState>=2&&video.videoWidth>0;
  if(live&&(canvas.width!==video.videoWidth||canvas.height!==video.videoHeight)){
    canvas.width=video.videoWidth;canvas.height=video.videoHeight;
  }
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if(live)ctx.drawImage(video,0,0,canvas.width,canvas.height);
  else if(preview)ctx.drawImage(preview,0,0,canvas.width,canvas.height);
  const [x,y,w,h]=roi;ctx.strokeStyle='#73e3bf';ctx.lineWidth=3;ctx.strokeRect(x*canvas.width,y*canvas.height,w*canvas.width,h*canvas.height);
  ctx.font='18px Dana, sans-serif';ctx.direction='rtl';ctx.textAlign='right';ctx.fillStyle='#73e3bf';ctx.fillText('جایگاه ثابت بطری',Math.min(canvas.width-8,(x+w)*canvas.width),Math.max(22,y*canvas.height-8));
}
async function showImage(data,epoch=null){
  const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=data;});
  if(epoch!==null&&epoch!==loopEpoch)return;preview=img;canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;draw();
}
function stopVideoPreview(){
  if(previewAnimation!==null){cancelAnimationFrame(previewAnimation);previewAnimation=null;}
  tabletViewer?.stop();tabletViewer=null;
  if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}
  $('video').pause?.();$('video').srcObject=null;$('video').hidden=true;
}
function keepPreviewLive(){
  if(previewAnimation!==null)return;
  const tick=now=>{
    if(!token||!$('video').srcObject){previewAnimation=null;return;}
    if(now-lastPreviewPaint>=80){lastPreviewPaint=now;draw();}
    previewAnimation=requestAnimationFrame(tick);
  };
  previewAnimation=requestAnimationFrame(tick);
}
async function showTabletVideo(){
  if(tabletViewer?.active&&$('video').srcObject){try{await tabletViewer.play();return;}catch{}}
  stopVideoPreview();
  if(!window.SmartShelfRTC)throw new Error('صفحه را دوباره باز کنید تا ابزار WebRTC بارگذاری شود.');
  tabletViewer=new window.SmartShelfRTC.Viewer({video:$('video'),getToken:()=>token,
    onState:(state,text)=>{$('video').hidden=!['live','play'].includes(state);$('videoStatus').textContent=text;},
    onStats:stats=>{if(stats.width)$('videoStatus').textContent=`WebRTC · ${stats.width}×${stats.height} · ${stats.fps.toFixed(1)} FPS`;}});
  await tabletViewer.start();
  keepPreviewLive();
}
async function openCamera(){
  if(tabletViewer){tabletViewer.stop();tabletViewer=null;}

  if(!stream?.getVideoTracks().some(t=>t.readyState==='live')){stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});$('video').srcObject=stream;}
  $('video').hidden=false;await $('video').play();keepPreviewLive();
}
function capture(){
  const v=$('video');if(!v.videoWidth||v.readyState<2)throw new Error('تصویر دوربین هنوز آماده نیست.');
  const c=document.createElement('canvas'),scale=Math.min(1,1280/Math.max(v.videoWidth,v.videoHeight));c.width=Math.round(v.videoWidth*scale);c.height=Math.round(v.videoHeight*scale);c.getContext('2d').drawImage(v,0,0,c.width,c.height);return c.toDataURL('image/jpeg',.86);
}
function updateFrameButtons(){
  $('startCamera').disabled=working||controlBusy;
  $('startCamera').textContent=working?(framesConfirmed?'ارسال تصویر فعال است':'در حال بررسی ارسال…'):'شروع ارسال تصویر';
  $('stopCamera').disabled=controlBusy||(!working&&$('cameraSource').value!=='tablet');
}
async function stopFrames(remote=false){
  working=false;framesConfirmed=false;loopEpoch++;controller?.abort();controller=null;
  $('cameraStatus').textContent='بررسی ارسال تصویر متوقف است؛ موجودی، آخرین مقدار ثبت‌شده است.';
  if(remote&&$('cameraSource').value==='tablet'){
    controlBusy=true;updateFrameButtons();
    try{
      if(!tabletViewer?.active)throw new Error('اتصال کنترل تبلت برقرار نیست؛ توقف از تبلت تأیید نشده است.');
      await tabletViewer.setProcessing(false);
      $('cameraStatus').textContent='تبلت توقف ارسال فریم هوش مصنوعی را تأیید کرد؛ ویدیوی زنده ادامه دارد.';
    }catch(error){$('cameraStatus').textContent='توقف ارسال از تبلت تأیید نشد.';notice(error.message);}
    finally{controlBusy=false;updateFrameButtons();}
  }
  updateFrameButtons();
}
async function cameraStatus(signal){
  const response=await fetch(SmartShelfApi.apiUrl('/api/admin/camera/status'),{headers:{Authorization:`Bearer ${token}`},cache:'no-store',signal});
  if(response.status===401){token='';sessionStorage.removeItem('smartshelf_admin_token');$('loginCard').hidden=false;stopFrames();stopVideoPreview();throw new Error('برای کنترل دوربین دوباره وارد پنل شوید.');}
  if(!response.ok)throw new Error(`وضعیت دریافت تصویر تأیید نشد (${response.status}).`);
  return response.json();
}
async function startFrames(){
  if(working||controlBusy)return;
  working=true;framesConfirmed=false;const epoch=++loopEpoch;updateFrameButtons();notice('');
  $('cameraStatus').textContent='در حال شروع ارسال تصویر…';
  const current=()=>working&&epoch===loopEpoch;
  try{
    if($('cameraSource').value==='tablet'){
      await showTabletVideo();if(!current())return;
      $('cameraStatus').textContent='در حال فرستادن فرمان شروع به تبلت…';
      await tabletViewer.setProcessing(true,current);if(!current())return;
      let lastCount=null,lastDevice=null,lastProgress=Date.now();
      $('cameraStatus').textContent='تبلت فرمان شروع را تأیید کرد؛ منتظر رسیدن فریم تازه به سرور…';
      while(current()){
        let timer=null;
        try{
          controller=new AbortController();const pending=controller;timer=setTimeout(()=>pending.abort(),10000);
          const stats=await cameraStatus(controller.signal);if(!current())break;
          const d=await api('/api/shop/status',{signal:controller.signal});if(!current())break;
          render(d.shop);
          const sameDevice=stats.device_id===tabletViewer?.deviceId;
          const advanced=sameDevice&&stats.is_live&&lastDevice===stats.device_id&&lastCount!==null&&stats.frame_count>lastCount;
          if(advanced){lastProgress=Date.now();framesConfirmed=true;}
          if(!sameDevice||!stats.is_live||Date.now()-lastProgress>=4000)framesConfirmed=false;
          const fresh=framesConfirmed;updateFrameButtons();
          lastCount=stats.frame_count;lastDevice=stats.device_id;
          if(fresh){
            const detail=!d.shop.enabled?'برای ثبت موجودی و سبد، سناریوی دانشگاهی را فعال کنید.':d.shop.camera_source!=='tablet'?'سناریو برای دوربین همین دستگاه تنظیم شده است؛ منبع سناریو را بررسی کنید.':d.shop.camera_live?'تشخیص برداشت و برگشت فعال است.':'فریم می‌رسد؛ در انتظار پردازش سناریو…';
            $('cameraStatus').textContent=`فریم تازهٔ تبلت به سرور رسید · ${fa(stats.frame_count)} فریم · ${stats.fps||0} FPS پردازش. ${detail}`;
          }else if(!sameDevice)$('cameraStatus').textContent='تصویر سرور متعلق به دوربین دیگری است؛ فریم همین تبلت هنوز تأیید نشده است.';
          else if(Date.now()-lastProgress>=4000)$('cameraStatus').textContent='ویدیو برقرار است، اما فریم تازهٔ هوش مصنوعی به سرور نمی‌رسد؛ وضعیت ارسال در صفحهٔ تبلت را بررسی کنید.';
          else $('cameraStatus').textContent='در انتظار تأیید یک فریم تازه از همین تبلت…';
        }catch(error){if(current()){framesConfirmed=false;updateFrameButtons();$('cameraStatus').textContent='دریافت فریم از سرور تأیید نشد؛ تلاش مجدد خودکار…';notice(error.name==='AbortError'?'پاسخ سرور دیر رسید.':error.message);}}
        finally{clearTimeout(timer);}
        if(current())await new Promise(resolve=>setTimeout(resolve,1200));
      }
      return;
    }
    if(!state?.enabled||state.camera_source!=='browser')throw new Error('ابتدا محصول و جایگاه را مشخص و سناریوی دانشگاهی را برای دوربین همین دستگاه فعال کنید.');
    await openCamera();if(!current()){stopVideoPreview();return;}
    while(current()){
      let timer=null;
      try{
        const data=capture();controller=new AbortController();const pending=controller;timer=setTimeout(()=>pending.abort(),15000);
        const r=await api('/api/shop/frame',{method:'POST',signal:controller.signal,body:JSON.stringify({frame:data,stream_id:streamId,sequence:++sequence})});
        if(!current())break;
        await showImage(data,epoch);if(r.shop)render(r.shop);
        framesConfirmed=true;updateFrameButtons();
        $('cameraStatus').textContent='تصویر زنده ارسال می‌شود؛ برداشت و برگشت در سرور بررسی می‌شوند.';notice('');
      }catch(error){if(current()){$('cameraStatus').textContent='در انتظار تصویر یا اتصال…';notice(error.message||'ارتباط قطع شد؛ تلاش دوباره انجام می‌شود.');}}
      finally{clearTimeout(timer);}
      if(current())await new Promise(resolve=>setTimeout(resolve,450));
    }
  }catch(error){if(current()){await stopFrames();$('cameraStatus').textContent='شروع ارسال تصویر تأیید نشد.';notice(error.message||'ارسال تصویر شروع نشد؛ وضعیت دوربین را بررسی کنید.');}}
  finally { if(epoch===loopEpoch&&!working)updateFrameButtons(); }
}
function point(event){const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))];}
canvas.addEventListener('pointerdown',e=>{if(state?.enabled||!preview)return;e.preventDefault();drag=point(e);canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{if(!drag)return;const p=point(e);roi=[Math.min(p[0],drag[0]),Math.min(p[1],drag[1]),Math.abs(p[0]-drag[0]),Math.abs(p[1]-drag[1])];draw();});
canvas.addEventListener('pointerup',()=>{if(drag){drag=null;$('roiConfirmed').checked=false;}});
canvas.addEventListener('pointercancel',()=>{drag=null;});
$('product').onchange=()=>{$('price').value=String(products.find(p=>p.id===Number($('product').value))?.unit_price||0);};
$('openCamera').onclick=async()=>{try{if($('cameraSource').value==='tablet')await showTabletVideo();else await openCamera();notice('');}catch(e){notice(e.message);}};
$('capture').onclick=async()=>{try{if($('cameraSource').value==='tablet'){if(!tabletViewer?.active||$('video').readyState<2)throw new Error('ابتدا «نمایش دوربین» را بزنید و منتظر ویدیوی زنده بمانید.');await showImage(capture());}else{await openCamera();await showImage(capture());}notice('اکنون دور جایگاه بطری روی میز کادر بکشید.');}catch(e){notice(e.message);}};
$('stopVideo').onclick=stopVideoPreview;
$('cameraSource').onchange=()=>{stopFrames();stopVideoPreview();};
$('startCamera').onclick=startFrames;$('stopCamera').onclick=()=>stopFrames(true);
function setScenarioBusy(busy){
  scenarioBusy=busy;
  $('enable').disabled=busy||Boolean(state?.session_id&&state?.enabled);
  $('disable').disabled=busy||!state?.enabled;
  $('cameraSource').disabled=busy||Boolean(state?.enabled);
}
$('enable').onclick=async()=>{
  if(scenarioBusy)return;
  setScenarioBusy(true);
  try{
    const price=Number(SmartShelfFormat.normalizeDigits($('price').value));
    if(!Number.isInteger(price)||price<0)throw new Error('قیمت نمایشی باید یک عدد صحیح نامنفی باشد.');
    const d=await api('/api/shop/configure',{method:'POST',body:JSON.stringify({
      enabled:true,product_id:Number($('product').value),zone_id:Number($('zone').value),
      unit_price:price,camera_source:$('cameraSource').value,roi,roi_confirmed:$('roiConfirmed').checked
    })});
    render(d.shop);
    notice('سناریو فعال شد؛ ارسال پیوستهٔ تصویر به‌صورت خودکار آغاز می‌شود.');
    // The calibration snapshot is not the AI frame stream.
    // Enabling the scenario starts the actual stream without a second click.
    startFrames();
  }catch(e){notice(e.message);}
  finally{setScenarioBusy(false);}
};
$('disable').onclick=async()=>{
  if(scenarioBusy)return;
  setScenarioBusy(true);
  // Cancel the local loop first, but retain the WebRTC control channel
  // until the stop command is acknowledged by the tablet.
  stopFrames();
  const viewer=tabletViewer;
  const stopTablet=viewer?.active&&$('cameraSource').value==='tablet'
    ? viewer.setProcessing(false,()=>!working).then(()=>true,()=>false)
    : Promise.resolve(false);
  try{
    // Server-side stop is independent of the tablet and must be immediate.
    const d=await api('/api/shop/configure',{method:'POST',body:JSON.stringify({enabled:false})});
    render(d.shop);
    notice('سناریو در سرور متوقف شد؛ در حال توقف ارسال فریم تبلت…');
  }catch(e){notice(e.message);}
  finally{
    // Do not leave the interface waiting 22 seconds for a lost WebRTC link.
    const stopped=await Promise.race([
      stopTablet,
      new Promise(resolve=>setTimeout(()=>resolve(false),3500))
    ]);
    if(viewer===tabletViewer)stopVideoPreview();
    if(state&&!state.enabled)notice(stopped||$('cameraSource').value!=='tablet'
      ? 'سناریو و ارسال تصویر متوقف شدند.'
      : 'سناریو در سرور متوقف شد؛ تأیید توقف از تبلت نرسید. ارسال را در صفحهٔ تبلت نیز متوقف کنید.');
    setScenarioBusy(false);
  }
};
$('loginForm').onsubmit=async event=>{event.preventDefault();try{const response=await fetch(SmartShelfApi.apiUrl('/api/admin/login'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:SmartShelfFormat.normalizeDigits($('pin').value.trim())})});const d=await response.json();if(!response.ok||!d.token)throw new Error(typeof d.detail==='string'?d.detail:'ورود ناموفق بود.');token=d.token;sessionStorage.setItem('smartshelf_admin_token',token);$('pin').value='';$('loginCard').hidden=true;await loadStatus(true);connect();notice('');}catch(e){notice(e.message);}};
freshTimer=setInterval(()=>{if(working&&state?.enabled&&Date.now()-lastShopUpdate>5000)$('cameraStatus').textContent='تصویر تازه نداریم؛ مقدار موجودی، آخرین مقدار ثبت‌شده است و نبودن تصویر خرید ایجاد نمی‌کند.';},2000);
window.addEventListener('pagehide',()=>{stopVideoPreview();token='';stopFrames();clearInterval(freshTimer);clearTimeout(qrTimer);clearTimeout(reconnect);socket?.close();stream?.getTracks().forEach(t=>t.stop());});
updateFrameButtons();
if(token){loadStatus(true).then(connect).catch(e=>notice(e.message));}else $('loginCard').hidden=false;

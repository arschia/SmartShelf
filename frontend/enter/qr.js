/* Local QR decoding; camera frames never leave the customer's browser. */
(function(root){
  'use strict';
  function normalize(raw){return root.SmartShelfFormat.normalizeDigits(String(raw||'')).replace(/[\s\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff]/g,'');}
  function tokenFromInput(raw){
    let value=normalize(raw);
    if(/^https?:\/\//i.test(value)||value.startsWith('/')){
      const link=new URL(value,root.location.origin);
      if(link.origin!==root.location.origin||!/^\/enter\/?$/.test(link.pathname)||link.username||link.password)throw new Error('این QR مربوط به ورود همین فروشگاه نیست.');
      value=normalize(link.searchParams.get('token'));
    }
    if(!/^[A-Za-z0-9_-]{6,128}$/.test(value))throw new Error('کد ورود معتبر نیست؛ عدد شش‌رقمی بالای QR را وارد کنید.');
    return value;
  }
  function attach(onToken){
    const $=id=>document.getElementById(id),video=$('entryQrVideo'),canvas=document.createElement('canvas'),context=canvas.getContext('2d',{willReadFrequently:true});
    let stream=null,timer=null,epoch=0;
    function stop(){epoch++;clearTimeout(timer);stream?.getTracks().forEach(track=>track.stop());stream=null;video.srcObject=null;video.hidden=true;$('stopQrScanBtn').hidden=true;$('scanQrBtn').disabled=false;}
    async function start(){
      stop();const own=epoch;$('scanQrBtn').disabled=true;$('stopQrScanBtn').hidden=false;$('qrScanStatus').textContent='در حال بازکردن دوربین…';
      try{
        if(!navigator.mediaDevices?.getUserMedia)throw new Error('دوربین در دسترس نیست؛ کد عددی را وارد کنید.');
        const next=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
        if(own!==epoch){next.getTracks().forEach(t=>t.stop());return;}
        stream=next;video.srcObject=next;video.hidden=false;await video.play();
        if(own!==epoch)return;
        $('qrScanStatus').textContent='QR ورودِ نمایش‌داده‌شده در پنل فروشگاه را مقابل دوربین بگیرید.';
        function scan(){
          if(own!==epoch)return;
          try{
            if(video.readyState>=2&&video.videoWidth){
              const scale=Math.min(1,640/video.videoWidth);canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
              context.drawImage(video,0,0,canvas.width,canvas.height);
              const image=context.getImageData(0,0,canvas.width,canvas.height),qr=root.jsQR(image.data,image.width,image.height,{inversionAttempts:'attemptBoth'});
              if(qr){const token=tokenFromInput(qr.data);stop();$('qrScanStatus').textContent='کد خوانده شد؛ در حال ورود به خرید…';onToken(token);return;}
            }
          }catch(error){$('qrScanStatus').textContent=error.message;}
          timer=setTimeout(scan,180);
        }
        scan();
      }catch(error){if(own===epoch){stop();$('qrScanStatus').textContent=error.name==='NotAllowedError'?'اجازهٔ دوربین داده نشد؛ مجوز دوربین را فعال کنید یا کد عددی را وارد کنید.':error.message;}}
    }
    $('scanQrBtn').onclick=start;$('stopQrScanBtn').onclick=()=>{stop();$('qrScanStatus').textContent='اسکن متوقف شد؛ می‌توانید کد عددی را وارد کنید.';};
    root.addEventListener('pagehide',stop);
    return {stop};
  }
  root.SmartShelfEntryQr={tokenFromInput,normalize,attach};
})(window);

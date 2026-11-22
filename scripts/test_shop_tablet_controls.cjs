// User action regression: Start must command the tablet AND observe new server
// frames. WebRTC video, an old snapshot or another camera cannot prove delivery.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<120;i++){if(fn())return;await wait(5);}throw new Error('Timed out');}
function environment(mode='live'){
  const nodes=new Map(),commands=[];let polls=0,videoStops=0,posts=0,release=null;
  const ctx={clearRect(){},drawImage(){},strokeRect(){},fillText(){}};
  function element(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:false,children:[],checked:false,disabled:false,
    getContext:()=>ctx,replaceChildren(){this.children=[];},appendChild(c){this.children.push(c);},addEventListener(){},pause(){}});return nodes.get(id);}
  const shop={enabled:true,camera_source:'tablet',roi:[0,0,1,1],session_id:1,cart:{items:[]},state:'PRESENT',camera_live:true,stock_quantity:1};
  class Viewer{
    constructor(options){this.options=options;this.active=false;this.deviceId='paired-tablet';}
    start(){this.active=true;this.options.video.srcObject={};}
    stop(){videoStops++;this.active=false;}
    async play(){}
    async setProcessing(enabled){commands.push(enabled);if(mode==='rejected')throw new Error('tablet refused command');return {enabled};}
  }
  class WebSocket{static OPEN=1;static CONNECTING=0;constructor(){this.readyState=0;}close(){}send(){}}
  const sandbox=vm.createContext({document:{getElementById:element,createElement:()=>element('new')},
    window:{addEventListener(){},SmartShelfRTC:{Viewer}},sessionStorage:{getItem:()=>'',removeItem(){}},WebSocket,
    SmartShelfApi:{apiUrl:p=>'https://backend.invalid'+p,wsUrl:p=>'wss://backend.invalid'+p},crypto:{randomUUID:()=> 'test'},
    SmartShelfFormat:{normalizeDigits:s=>s},Date,AbortController,console,clearTimeout,setInterval:()=>1,clearInterval(){},
    setTimeout:(fn,ms)=>setTimeout(fn,ms>=10000?10000:Math.min(ms,15)),
    fetch:async(url,options)=>{
      assert.equal(options.headers.Authorization,'Bearer admin');if(url.endsWith('/api/shop/frame'))posts++;
      if(url.endsWith('/api/shop/stream')){
        commands.push('wss:'+JSON.parse(options.body).enabled);
        return {ok:true,json:async()=>({command_sent:true,device_id:'paired-tablet'})};
      }
      if(url.endsWith('/api/shop/configure')){
        const payload=JSON.parse(options.body);
        shop.enabled=payload.enabled;
        return {ok:true,json:async()=>({shop})};
      }
      if(url.endsWith('/api/admin/camera/status')){
        polls++;if(mode==='late')await new Promise(resolve=>{release=resolve;});
        return {ok:true,json:async()=>({device_id:mode==='other'?'another-tablet':'paired-tablet',frame_count:mode==='frozen'?10:polls+10,is_live:true,fps:5})};
      }
      assert(url.endsWith('/api/shop/status'));return {ok:true,json:async()=>({shop,products:[]})};
    }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/shop.js'),'utf8'),sandbox);
  sandbox.initial=shop;vm.runInContext('token="admin";render(initial)',sandbox);element('cameraSource').value='tablet';
  return {run:code=>vm.runInContext(code,sandbox),element,commands,polls:()=>polls,videoStops:()=>videoStops,posts:()=>posts,release:()=>release?.()};
}
(async()=>{
  const live=environment(),running=live.run('startFrames()');
  await until(()=>live.element('cameraStatus').textContent.includes('فریم تازهٔ تبلت به سرور رسید'));
  assert.deepEqual(live.commands,[true,'wss:true']);assert.equal(live.element('startCamera').disabled,true);
  assert.equal(live.posts(),0,'admin must not submit duplicate WebRTC frames to the accounting pipeline');
  assert.match(live.element('cameraStatus').textContent,/تشخیص برداشت و برگشت فعال/);
  await live.element('stopCamera').onclick();await running;
  assert.deepEqual(live.commands,[true,'wss:true','wss:false',false]);assert.equal(live.videoStops(),0,'AI pause must preserve live video');assert.equal(live.element('startCamera').disabled,false);
  assert.match(live.element('cameraStatus').textContent,/فرمان توقف به سرور|توقف ارسال فریم/);

  // Operator buttons must start AI frames automatically and stop tablet
  // processing before the WebRTC viewer is released.
  const automatic=environment();
  automatic.run('initial.enabled=false;render(initial)');
  automatic.element('cameraSource').value='tablet';
  automatic.element('roiConfirmed').checked=true;
  await automatic.element('enable').onclick();
  await until(()=>automatic.commands.includes(true)&&automatic.polls()>0);
  assert.equal(automatic.element('startCamera').disabled,true,'auto-start should own the loop');
  await automatic.element('disable').onclick();
  assert.deepEqual(automatic.commands,[true,'wss:true',false],'scenario stop must send remote stop');
  assert(automatic.videoStops()>0,'viewer must be released after stop acknowledgment');
  assert.equal(automatic.element('disable').disabled,true,'stopped scenario cannot stop twice');

  for(const mode of ['frozen','other']){
    const e=environment(mode),running=e.run('startFrames()');await until(()=>e.polls()>=3);
    assert(!e.element('cameraStatus').textContent.includes('فریم تازهٔ تبلت به سرور رسید'),mode+' must never claim success');
    if(mode==='other')assert.match(e.element('cameraStatus').textContent,/دوربین دیگری/);
    await e.run('stopFrames()');await running;
  }
  const rejected=environment('rejected'),fallback=rejected.run('startFrames()');
  await until(()=>rejected.polls()>=3);
  assert(rejected.commands.includes('wss:true'),'WebRTC failure must not block server-controlled JPEG frames');
  assert.match(rejected.element('videoStatus').textContent,/JPEG/);
  await rejected.run('stopFrames()');await fallback;

  const late=environment('late'),pending=late.run('startFrames()');await until(()=>late.polls()===1);
  await late.run('stopFrames()');late.release();await pending;
  assert(!late.element('cameraStatus').textContent.includes('فریم تازهٔ تبلت به سرور رسید'),'late response after Stop must not revive success');
  console.log('PASS: real shop Start/Stop: acknowledged remote control, new frames from bound tablet, frozen/other-camera rejection, no duplicate billing frames, visible errors and cancellation.');
})().catch(error=>{console.error(error);process.exitCode=1;});

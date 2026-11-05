// Exercise actual camera startup through browser boundaries, including the old
// failure after a successful grant (the removed WebRTC callback is not mocked).
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function environment({errors=[],playErrors=[]}={}){
  const elements=new Map(),storage=new Map([['smartshelf_device_id','startup_tablet']]),calls=[],tracks=[];
  function element(id){if(!elements.has(id))elements.set(id,{style:{},textContent:'',value:'',innerHTML:'',children:[],
    appendChild(x){this.children.push(x);},getContext:()=>({drawImage(){}}),addEventListener(){},
    play:async()=>{const error=playErrors.shift();if(error)throw error;},readyState:2});return elements.get(id);}
  const media={enumerateDevices:async()=>[],getUserMedia:async constraints=>{
    calls.push(constraints);const error=errors.shift();if(error)throw error;
    const track={readyState:'live',handler:null,addEventListener(_name,handler){this.handler=handler;},stop(){this.readyState='ended';this.handler?.();}};
    tracks.push(track);return {getTracks:()=>[track],getVideoTracks:()=>[track]};
  }};
  let intervals=0;
  const context=vm.createContext({document:{getElementById:element,createElement:element,addEventListener(){},documentElement:{}},
    navigator:{mediaDevices:media},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    window:null,Date,AbortController,URLSearchParams,console,setInterval:()=>++intervals,clearInterval(){},setTimeout,clearTimeout});
  context.window=context;context.isSecureContext=true;context.addEventListener=()=>{};
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/camera/app.js'),'utf8'),context);
  return {context,element,media,calls,tracks,run:code=>vm.runInContext(code,context),intervals:()=>intervals};
}
const error=name=>Object.assign(new Error(name),{name});
(async()=>{
  const good=environment();await good.run('initCamera()');
  assert.equal(good.element('cameraErrorBox').style.display,'none');
  assert.equal(good.run('lastCameraError'),null);assert.equal(good.intervals(),1);
  assert.equal(good.tracks[0].readyState,'live');
  assert.equal(good.run('setFrameTransmission(false)').enabled,false);
  assert.equal(good.tracks[0].readyState,'live','remote AI pause must preserve WebRTC camera');
  assert.equal(good.run('setFrameTransmission(true)').enabled,true);
  await good.run('initCamera()');
  assert.equal(good.tracks[0].readyState,'ended');assert.equal(good.element('cameraErrorBox').style.display,'none','intentional camera switch must not show a hardware failure');

  const busy=environment({errors:[error('NotReadableError')]});await busy.run('initCamera()');
  assert.match(busy.element('cameraErrorDesc').textContent,/دیگری/);assert.equal(busy.element('cameraErrorCode').textContent,'NotReadableError');

  const denied=environment({errors:[error('NotAllowedError')]});await denied.run('initCamera()');
  assert.equal(denied.calls.length,1,'do not repeatedly prompt for denied permission');
  assert.match(denied.element('cameraErrorDesc').textContent,/سیستم‌عامل/);

  const playback=environment({playErrors:[error('NotAllowedError')]});await playback.run('initCamera()');
  assert.match(playback.element('cameraErrorDesc').textContent,/پخش تصویر/);
  await playback.run('initCamera(null,true)');assert.equal(playback.calls.length,1,'retry playback using the already granted camera');
  assert.equal(playback.element('cameraErrorBox').style.display,'none');

  const fallback=environment({errors:[error('OverconstrainedError')]});await fallback.run('initCamera("stale-device-id")');
  assert.equal(fallback.calls.length,2);assert.equal(fallback.calls[1].video,true);assert.equal(fallback.element('cameraErrorBox').style.display,'none');

  const insecure=environment();insecure.context.isSecureContext=false;await insecure.run('initCamera()');
  assert.equal(insecure.calls.length,0);assert.equal(insecure.element('cameraErrorCode').textContent,'InsecureContext');
  assert(!insecure.element('cameraErrorDesc').textContent.includes('Flags'));
  console.log('PASS: granted camera starts capture; intentional switch; busy/permission/playback errors; playback retry reuses stream; unsupported constraints fall back; secure-context diagnosis.');
})().catch(error=>{console.error(error);process.exitCode=1;});

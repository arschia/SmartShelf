// Run the actual page code against controlled camera, DOM and network boundaries.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../frontend/bottle.js'),'utf8');
const flush = async () => {for(let i=0;i<12;i++)await new Promise(resolve=>setImmediate(resolve));};

function environment(responses=[]) {
  const elements=new Map(),timers=new Map(),requests=[],texts=[];
  let timerId=0,cameraStarts=0;
  const drawing={clearRect(){},drawImage(){},strokeRect(){},fillRect(){},measureText:t=>({width:t.length*8}),fillText:t=>texts.push(t)};
  function element(id) {
    if(!elements.has(id))elements.set(id,{value:id==='threshold'?'.35':id==='liveSource'?'local':id==='classId'?'0':'',checked:false,hidden:false,disabled:false,
      textContent:'',width:640,height:480,videoWidth:640,videoHeight:480,readyState:2,events:{},
      classList:{toggle(){}},getContext:()=>drawing,replaceChildren(){},appendChild(){},setPointerCapture(){},
      getBoundingClientRect:()=>({left:0,top:0,width:640,height:480}),play:async()=>{},toDataURL:()=> 'data:image/jpeg;base64,LOCAL_FRAME',
      addEventListener(name,callback){this.events[name]=callback;}});
    return elements.get(id);
  }
  const track={readyState:'live',stop(){this.readyState='ended';}};
  class FakeImage {
    constructor(){this.naturalWidth=640;this.naturalHeight=480;}
    set src(data){queueMicrotask(()=>{if(data)this.onload();else this.onerror();});}
  }
  const context=vm.createContext({document:{getElementById:element,createElement:name=>element('created-'+name)},
    sessionStorage:{getItem:()=>'',removeItem(){},setItem(){}},SmartShelfApi:{apiUrl:p=>'https://owned-backend.invalid'+p},
    SmartShelfFormat:{normalizeDigits:s=>s},Image:FakeImage,AbortController,URL,console,
    navigator:{mediaDevices:{getUserMedia:async()=>{cameraStarts++;return {getVideoTracks:()=>[track],getTracks:()=>[track]};}}},
    window:{addEventListener(){}},
    setTimeout(callback,ms){const id=++timerId;timers.set(id,{callback,ms});return id;},clearTimeout:id=>timers.delete(id),
    fetch:async(url,options={})=>{
      requests.push({url,options});const response=responses.shift();
      if(response instanceof Error)throw response;
      if(typeof response==='function')return response(options);
      const status=response?.status||200;
      return {ok:status>=200&&status<300,status,json:async()=>response?.body||result()};
    }});
  vm.runInContext(source,context);
  return {element,requests,texts,responses,run:code=>vm.runInContext(code,context),cameraStarts:()=>cameraStarts,
    tick:async()=>{const next=[...timers].find(([,timer])=>timer.ms<20000);assert(next,'expected retry/frame timer');timers.delete(next[0]);next[1].callback();await flush();}};
}
function result(){return {detections:[{box:[.1,.1,.6,.9],class_name:'bottle',confidence:.9}],bottle_count:1,target_count:0,elapsed_ms:50,mode:'generic_bottle',frame:'data:image/jpeg;base64,TABLET_FRAME'};}
async function finish(env,promise){env.run('stopLive()');await env.tick();await promise;}

(async()=>{
  const local=environment();const localRun=local.run('startLive()');await flush();
  assert.equal(local.cameraStarts(),1);
  assert.equal(JSON.parse(local.requests[0].options.body).source,'upload');
  assert.equal(JSON.parse(local.requests[0].options.body).frame,'data:image/jpeg;base64,LOCAL_FRAME');
  assert.equal(local.run('live'),true);
  assert.match(local.element('liveStatus').textContent,/دوربین همین دستگاه/);
  await finish(local,localRun);

  const tablet=environment([{status:409,body:{detail:'No tablet frame'}},{body:result()}]);
  tablet.element('liveSource').value='tablet';const tabletRun=tablet.run('startLive()');await flush();
  assert.equal(tablet.run('live'),true,'missing tablet frame must wait, not stop');
  assert.equal(tablet.cameraStarts(),0);
  assert.match(tablet.element('liveStatus').textContent,/انتظار/);
  await tablet.tick();assert.equal(tablet.requests.length,2);assert.equal(tablet.run('detections.length'),1);
  await finish(tablet,tabletRun);

  const network=environment([{body:result()},new TypeError('network offline'),{body:result()}]);
  network.element('liveSource').value='tablet';const networkRun=network.run('startLive()');await flush();
  await network.tick();assert.equal(network.run('live'),true);assert.equal(network.run('detections.length'),0,'stale detection must clear');
  await network.tick();assert.equal(network.run('detections.length'),1,'must recover automatically');
  await finish(network,networkRun);

  const auth=environment([{status:401,body:{detail:'expired'}}]);auth.element('liveSource').value='tablet';
  await auth.run('startLive()');assert.equal(auth.run('live'),false);assert.equal(auth.element('loginCard').hidden,false);

  const stopped=environment([options=>new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>{const e=new Error('cancelled');e.name='AbortError';reject(e);}))]);
  stopped.element('liveSource').value='tablet';const stoppedRun=stopped.run('startLive()');await flush();
  stopped.run('stopLive()');await stoppedRun;assert.equal(stopped.requests.length,1);assert.equal(stopped.run('live'),false);

  const labels=environment();await labels.run('setImage("data:image/jpeg;base64,IMAGE")');
  const point=(x,y)=>({clientX:x,clientY:y,pointerId:1,preventDefault(){}});
  labels.element('canvas').events.pointerdown(point(20,20));labels.element('canvas').events.pointerup(point(200,300));
  assert.equal(labels.run('boxes.length'),0,'drawing is disabled until explicitly enabled');
  labels.element('annotationMode').checked=true;labels.element('annotationMode').onchange();
  labels.element('canvas').events.pointerdown(point(20,20));labels.element('canvas').events.pointerup(point(200,300));
  assert.equal(labels.run('boxes.length'),1);assert.equal(labels.element('reviewed').checked,false);
  assert(labels.texts.some(text=>text.includes('برچسب دستی: هی‌جو هلو')));
  assert(!labels.texts.some(text=>/reviewed|Heyjo/.test(text)));
  console.log('PASS: local live camera; tablet waiting/recovery; network recovery and stale overlay clearing; auth stop; request cancellation; opt-in Persian manual labels.');
})().catch(error=>{console.error(error);process.exitCode=1;});

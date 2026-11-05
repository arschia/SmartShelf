const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function environment(){
  const elements=new Map(),timers=new Map(),intervals=new Map(),stored=new Map([['smartshelf_device_id','tablet_ui_test'],['smartshelf_device_token','test-device-token-123456789012345678901234567890']]);
  let id=0;
  const element=name=>{if(!elements.has(name))elements.set(name,{textContent:'',style:{},className:'',readyState:2,videoWidth:640,videoHeight:480,getContext:()=>({drawImage(){}}),toBlob:callback=>callback({jpeg:true}),addEventListener(){},remove(){}});return elements.get(name);};
  const connections=[];
  class WebSocket{static OPEN=1;static CONNECTING=0;constructor(){this.readyState=0;this.bufferedAmount=0;this.sent=[];connections.push(this);}send(value){this.sent.push(value);}close(code){this.readyState=3;this.onclose?.({code});}}
  const context=vm.createContext({document:{getElementById:element,createElement:element,addEventListener(){},documentElement:{}},localStorage:{getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)},
    window:null,WebSocket,SmartShelfApi:{wsUrl:p=>'wss://backend.invalid'+p,apiUrl:p=>'https://backend.invalid'+p},
    setTimeout:(cb,ms)=>{const value=++id;timers.set(value,{cb,ms});return value;},clearTimeout:k=>timers.delete(k),
    setInterval:(cb,ms)=>{const value=++id;intervals.set(value,{cb,ms});return value;},clearInterval:k=>intervals.delete(k),Date,AbortController,URLSearchParams,console,
    fetch:async()=>({ok:true,json:async()=>({type:'frame_received'})})});
  context.window=context;context.addEventListener=()=>{};
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/camera/app.js'),'utf8'),context);
  return {context,element,stored,timers,intervals,connections,run:code=>vm.runInContext(code,context)};
}
(async()=>{
  const hung=environment();hung.run('connectCameraWs()');assert.equal(hung.connections.length,1);
  [...hung.timers.values()].find(t=>t.ms===8000).cb();
  assert.equal(hung.run('cameraTransport'),'https');assert(hung.stored.has('smartshelf_device_token'),'network failures must not discard valid pairing');

  const e=environment();e.run('connectCameraWs();currentStream={getVideoTracks:()=>[{readyState:"live"}]};startFrameCapture()');
  const ws=e.connections[0],capture=[...e.intervals.values()].find(t=>t.ms===200).cb;
  ws.readyState=1;ws.onopen();assert.equal(JSON.parse(ws.sent[0]).frame_ack,true);
  capture();assert.equal(ws.sent.length,1,'never send JPEG before authentication acknowledgement');
  ws.onmessage({data:JSON.stringify({type:'connected',frame_ack:true})});
  capture();await new Promise(r=>setImmediate(r));assert.equal(ws.sent.length,2);assert.equal(e.run('framesSent'),0,'unacknowledged frame must not be counted as delivered');
  capture();assert.equal(ws.sent.length,2,'backpressure: only one unacknowledged frame');
  ws.onmessage({data:JSON.stringify({type:'frame_received',frame_count:1})});assert.equal(e.run('framesSent'),1);assert.match(e.element('wsStatusBadge').className,/online/);
  e.run('resetCameraConnection()');assert(e.stored.has('smartshelf_device_token'));

  const http=environment();http.run('useHttpsTransport();currentStream={getVideoTracks:()=>[{readyState:"live"}]};startFrameCapture()');
  [...http.intervals.values()].find(t=>t.ms===200).cb();for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));
  assert.equal(http.run('framesSent'),1);assert.match(http.element('cameraTransportDetail').textContent,/HTTPS/);
  console.log('PASS: hung WSS falls back to HTTPS; credentials survive network failures; auth before JPEG; frame acknowledgement and backpressure; HTTPS confirmed delivery.');
})().catch(e=>{console.error(e);process.exitCode=1;});

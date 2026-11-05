// Executes the actual Publisher/Viewer against browser and HTTP boundaries.
// This verifies negotiation/lifecycle, not real camera FPS or NAT traversal.
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(predicate){for(let n=0;n<150;n++){if(predicate())return;await wait(10);}throw new Error('Timed out');}
const sessions=new Map(),pcs=new Map(),http=[],states=[],stats=[];let next=0;
class Channel{
  constructor(label){this.label=label;this.readyState='connecting';}
  send(data){if(this.readyState!=='open')throw new Error('Channel closed');setImmediate(()=>this.remote?.onmessage?.({data}));}
  close(){this.readyState='closed';if(this.remote)this.remote.readyState='closed';}
}
class PC{
  constructor(config){this.id=++next;pcs.set(this.id,this);this.config=config;this.connectionState='new';this.senders=[];this.transceivers=[];this.frames=0;this.clock=0;this.channels=[];}
  createDataChannel(label){const channel=new Channel(label);this.channels.push(channel);return channel;}
  addTransceiver(kind,options){this.transceivers.push({kind,...options});}
  addTrack(track,stream){this.stream=stream;const sender={track,getParameters:()=>({encodings:[{}]}),setParameters:async p=>{sender.params=p;},replaceTrack:async t=>{sender.track=t;}};this.senders.push(sender);return sender;}
  getSenders(){return this.senders;}
  async createOffer(){return {type:'offer',sdp:String(this.id)};}
  async createAnswer(){return {type:'answer',sdp:String(this.id)};}
  async setLocalDescription(d){this.localDescription=d;this.onicecandidate?.({candidate:{toJSON:()=>({candidate:'local-ice',sdpMid:'0'})}});}
  async setRemoteDescription(d){this.remoteDescription=d;if(d.type==='offer'){for(const remote of pcs.get(Number(d.sdp)).channels){const channel=new Channel(remote.label);channel.remote=remote;remote.remote=channel;this.channels.push(channel);this.ondatachannel?.({channel});}}if(d.type==='answer'){this.remote=pcs.get(Number(d.sdp));this.remote.remote=this;this.connectionState=this.remote.connectionState='connected';for(const channel of this.channels){channel.readyState='open';channel.remote.readyState='open';}this.ontrack?.({streams:[this.remote.stream],track:this.remote.senders[0].track});this.onconnectionstatechange?.();this.remote.onconnectionstatechange?.();}}
  async addIceCandidate(){assert(this.remoteDescription,'must buffer remote ICE until the SDP arrives');}
  async getStats(){this.clock+=1000;if(this.connectionState==='connected')this.frames+=30;return new Map([['v',{type:'inbound-rtp',kind:'video',framesDecoded:this.frames,timestamp:this.clock,framesPerSecond:30,frameWidth:1280,frameHeight:720}]]);}
  close(){this.connectionState='closed';for(const channel of this.channels)channel.close();}
}
const track=()=>({kind:'video',readyState:'live',stop(){throw new Error('WebRTC must never stop the shared vision camera');}});
const stream=t=>({getVideoTracks:()=>[t],getTracks:()=>[t]});
const video={srcObject:null,videoWidth:1280,videoHeight:720,play:async()=>{},pause(){}};
async function fetch(url,options={}){
  http.push({url,options});assert(!url.includes('admin-secret')&&!url.includes('device-secret'));
  const admin=options.headers.Authorization==='Bearer admin-secret';
  assert(admin||options.headers.Authorization==='Bearer device-secret');
  const u=new URL(url),p=u.pathname.replace('/api/rtc',''),data=options.body?JSON.parse(options.body):{};let result;
  if(p==='/view'){
    assert(admin);const sid='session-'+(++next);sessions.set(sid,{camera:[],viewer:[],cs:0,vs:0,closed:false});result={session_id:sid,device_id:'tablet',ice_servers:[]};
  }else if(p==='/camera/poll'){
    assert(!admin);result={ice_servers:[],sessions:[...sessions].map(([sid,s])=>({session_id:sid,messages:s.camera.filter(e=>e.seq>(data.after?.[sid]||0)),closed:s.closed}))};
  }else{
    const [,side,sid,action]=p.split('/'),s=sessions.get(sid);assert(s,'session exists');
    if(action==='signal'){
      assert.equal(admin,side==='view');const dest=side==='view'?'camera':'viewer',counter=dest==='camera'?'cs':'vs';
      s[dest].push({...data,seq:++s[counter]});if(data.type==='close')s.closed=true;result={ok:true};
    }else{assert(admin);result={messages:s.viewer.filter(e=>e.seq>Number(u.searchParams.get('after')||0)),closed:s.closed};}
  }
  return {ok:true,json:async()=>result};
}
const sandbox={window:null,RTCPeerConnection:PC,fetch,AbortController,console,
  setTimeout:(fn,ms)=>setTimeout(fn,ms===8000?8000:Math.min(ms,20)),clearTimeout,
  SmartShelfApi:{apiUrl:p=>'https://backend.invalid'+p}};
sandbox.window=sandbox;
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../frontend/assets/js/rtc.js'),'utf8'),sandbox);
(async()=>{
  const controlCalls=[];
  const {Publisher,Viewer}=sandbox.SmartShelfRTC,original=track(),publisher=new Publisher({deviceId:'tablet',getToken:()=> 'device-secret',onControl:enabled=>{controlCalls.push(enabled);return {enabled};}});
  await publisher.setStream(stream(original));publisher.start();
  const viewer=new Viewer({video,getToken:()=> 'admin-secret',onState:(state,message)=>states.push({state,message}),onStats:s=>stats.push(s)});
  viewer.start();await until(()=>stats.length>1);
  assert(states.some(s=>s.state==='live'));assert.equal(stats.at(-1).fps,30);assert.equal(stats.at(-1).width,1280);
  assert(video.srcObject,'must attach a MediaStream, not a JPEG URL');
  const peer=[...publisher.peers.values()][0],sender=peer.pc.getSenders()[0];
  assert.equal(sender.track,original);assert.equal(sender.params.encodings[0].maxFramerate,30);assert.equal(sender.params.encodings[0].maxBitrate,2500000);
  assert.equal(viewer.peer.pc.transceivers.length,1);assert.equal(viewer.peer.pc.transceivers[0].kind,'video');assert.equal(viewer.peer.pc.transceivers[0].direction,'recvonly');
  assert.equal((await viewer.setProcessing(false)).enabled,false);assert.equal((await viewer.setProcessing(true)).enabled,true);
  assert.deepEqual(controlCalls,[false,true]);assert.equal(video.srcObject.getVideoTracks()[0],original,'AI pause must not stop WebRTC preview');
  publisher.onControl=()=>{throw new Error('camera not ready');};
  await assert.rejects(viewer.setProcessing(true),/camera not ready/);
  const changed=track();await publisher.setStream(stream(changed));assert.equal(sender.track,changed,'switch camera via replaceTrack');
  publisher.setEnabled(false);await until(()=>states.some(s=>s.state==='error'));
  assert.equal(video.srcObject,null,'a frozen video must not remain labeled live');assert.equal(publisher.peers.size,0);
  viewer.stop();publisher.stop();
  assert.equal(original.readyState,'live');assert.equal(changed.readyState,'live','viewer lifecycle must not stop AI frames');
  assert(http.some(r=>r.url.includes('/camera/poll')));assert(!http.some(r=>r.url.includes('latest-frame')));
  const first=[...sessions.values()][0];assert.equal(first.camera[0].type,'offer','SDP must precede local ICE');assert.equal(first.viewer[0].type,'answer');
  const sessionCount=sessions.size,stale=new Viewer({video,getToken:()=> 'admin-secret'});
  const starting=stale.start();stale.stop();await starting;await until(()=>[...sessions.values()].at(-1).closed);
  assert.equal(sessions.size,sessionCount+1);assert.equal([...sessions.values()].at(-1).closed,true,'late session creation must be closed');
  console.log('PASS: actual RTC video and authenticated data channel: start/stop command acknowledgment, camera error rejection, independent preview, FPS, track replacement, cleanup and stale opens.');
})().catch(error=>{console.error(error);process.exitCode=1;});

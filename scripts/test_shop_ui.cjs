const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const elements=new Map(),connections=[];
const context={clearRect(){},drawImage(){},strokeRect(){},fillText(){}};
function element(id){if(!elements.has(id))elements.set(id,{textContent:'',value:'',hidden:false,checked:false,disabled:false,children:[],classList:{},
  getContext:()=>context,replaceChildren(){this.children=[];},appendChild(child){this.children.push(child);},prepend(child){this.children.unshift(child);},addEventListener(){}});return elements.get(id);}
class WebSocket{static OPEN=1;static CONNECTING=0;constructor(){this.readyState=0;connections.push(this);}send(){}close(){}}
let serverState=null,statusReads=0,qrCount=0;
const sandbox=vm.createContext({document:{getElementById:element,createElement:tag=>element(tag+Math.random())},
  sessionStorage:{getItem:()=>'',setItem(){},removeItem(){}},crypto:{randomUUID:()=> 'unit-stream'},WebSocket,
  SmartShelfApi:{apiUrl:p=>'https://backend.invalid'+p,wsUrl:p=>'wss://backend.invalid'+p},
  SmartShelfFormat:{normalizeDigits:s=>s},window:{addEventListener(){}},Date,AbortController,console,
  setInterval:()=>1,clearInterval(){},setTimeout:()=>1,clearTimeout(){},QRCode:function(){qrCount++;},
  fetch:async(url)=>{assert(url.endsWith('/api/shop/status'));statusReads++;return {ok:true,json:async()=>({shop:serverState,products:[],zones:[]})};}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/shop.js'),'utf8'),sandbox);
const state=(stock,qty)=>({enabled:true,needs_review:false,camera_source:'browser',roi:[0,0,1,1],product_id:1,product_name:'هی‌جو هلو',unit_price:10000,stock_quantity:stock,session_id:1,state:stock?'PRESENT':'ABSENT',cart:{total_quantity:qty,grand_total:qty*10000,items:qty?[{product_name:'هی‌جو هلو',quantity:qty,line_total:qty*10000}]:[]}});
(async()=>{
  sandbox.first=state(1,0);vm.runInContext('render(first);token="test";connect()',sandbox);
  assert.equal(element('stock').textContent,'۱');assert.equal(element('quantity').textContent,'۰');
  const ws=connections[0];ws.onmessage({data:JSON.stringify({type:'SHOP_STATE',shop:state(0,1)})});
  assert.equal(element('stock').textContent,'۰');assert.equal(element('quantity').textContent,'۱');
  assert.equal(qrCount,0,'active customer snapshots must not regenerate entry QR');
  serverState=state(1,0);ws.onmessage({data:JSON.stringify({type:'CART_UPDATED'})});
  for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));
  assert.equal(statusReads,1);assert.equal(element('stock').textContent,'۱');assert.equal(element('quantity').textContent,'۰');
  let rtcStarts=0,rtcStops=0;
  sandbox.window.SmartShelfRTC={Viewer:class {
    constructor(options){this.options=options;this.active=false;}
    start(){rtcStarts++;this.active=true;this.options.video.srcObject={};this.options.onState('live','WebRTC');this.options.onStats({fps:28.3,width:1280,height:720});}
    stop(){rtcStops++;this.active=false;}
    async play(){}
  }};
  element('cameraSource').value='tablet';
  await element('openCamera').onclick();
  assert.equal(rtcStarts,1,'Show camera must open WebRTC');
  assert.equal(statusReads,1,'Show camera must not request a still image or run bottle detection');
  assert.match(element('videoStatus').textContent,/28.3 FPS/);
  assert.equal(element('video').hidden,false);
  element('stopVideo').onclick();assert.equal(rtcStops,1);assert.equal(element('video').hidden,true);
  assert(!fs.readFileSync(path.join(__dirname,'../frontend/admin/index.html'),'utf8').includes('btnSimulatePick'));
  console.log('PASS: actual live-shop WebSocket handler updates stock/cart without navigation or refresh; legacy simulator removed.');
})().catch(e=>{console.error(e);process.exitCode=1;});

// A phone must recover missed cart updates without overwriting newer socket data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
const document = {
  addEventListener() {},
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, {style: {}});
    return elements.get(id);
  }
};
let release;
const ctx = vm.createContext({
  document, window: {}, AbortController, clearInterval, clearTimeout, setTimeout, console,
  fetch: () => new Promise(resolve => { release = cart => resolve({ok:true, json:async () => cart}); })
});
vm.runInContext(fs.readFileSync('frontend/customer/app.js', 'utf8'), ctx);
const run = code => vm.runInContext(code, ctx);
(async () => {
  run('currentSessionSecret="customer"; renderCart = data => { latestCart=data; }');
  let pending = run('fetchLiveCart(currentSessionSecret)');
  release({items:[{quantity:1}], grand_total:12});
  await pending;
  assert.equal(run('latestCart.grand_total'),12);
  pending = run('fetchLiveCart(currentSessionSecret)');
  run('cartRevision++; renderCart({items:[], grand_total:0})');
  release({items:[{quantity:1}], grand_total:12});
  await pending;
  assert.equal(run('latestCart.grand_total'),0);
  pending = run('fetchLiveCart(currentSessionSecret)');
  release({session_closed:true});
  await pending;
  assert.equal(run('currentSessionSecret'),null);
  assert.equal(document.getElementById('stateClosed').style.display,'block');
  console.log('PASS: phone cart recovery, late response ordering and session closure.');
})().catch(error => { console.error(error); process.exitCode=1; });

// Exercise the actual browser handlers with controlled DOM/network boundaries.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const format = require(path.join(root, 'frontend/assets/js/format.js'));

function handler(file, name) {
  const source = fs.readFileSync(path.join(root, file), 'utf8');
  const start = source.indexOf('async function ' + name + '(');
  assert(start >= 0);
  const end = source.indexOf('\n}', start) + 2;
  assert(end > start);
  return source.slice(start, end);
}

function environment() {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {value: '', textContent: '', style: {},
      removeAttribute(name) {delete this[name];}});
    return elements.get(id);
  };
  const stored = new Map();
  const context = {document: {getElementById: element},
    SmartShelfFormat: format, SmartShelfApi: {apiUrl: p => 'https://backend.invalid' + p},
    localStorage: {setItem: (k,v) => stored.set(k,v), removeItem: k => stored.delete(k)},
    location: {origin: 'https://shelf-ir.vercel.app'}, deviceId: 'ui_test_tablet',
    pairedCode: '', tabletPairedOnline: false, pairingTimerInterval: null,
    updateWsBadge() {}, hidePairingModal() {}, connectCameraWs() {}, resetCameraConnection() {},
    tabletRtcPublisher:null, startTabletWebRTC() {},
    startListeningForTabletPair() {}, setInterval: () => 1, clearInterval() {},
    toasts: [], showToast(message, type) {context.toasts.push({message, type});}};
  context.window = context;
  return {context: vm.createContext(context), element, stored};
}

(async () => {
  const submit = handler('frontend/camera/app.js', 'submitPairingCode');
  for (const input of ['123456', '۱۲۳۴۵۶', '١٢٣٤٥٦', '\u200f۱۲۳ ۴۵۶\u200e']) {
    const e = environment(); let calls = 0;
    e.context.fetch = async (_url, options) => {
      calls++; const payload = JSON.parse(options.body);
      assert.equal(payload.code, '123456');
      assert.equal(payload.pairing_code, '123456');
      return {ok: true, json: async () => ({device_token: 'test-token'})};
    };
    e.element('pairingCodeInput').value = input;
    vm.runInContext(submit, e.context);
    await e.context.submitPairingCode();
    assert.equal(calls, 1);
    assert.equal(e.stored.get('smartshelf_device_token'), 'test-token');
  }
  for (const input of ['12345', '1234567', '123x456']) {
    const e = environment(); let called = false;
    e.context.fetch = async () => {called = true;};
    e.element('pairingCodeInput').value = input;
    vm.runInContext(submit, e.context);
    await e.context.submitPairingCode();
    assert.equal(called, false);
    assert.equal(e.element('pairingErrorMsg').style.display, 'block');
  }
  const generate = handler('frontend/admin/app.js', 'generateCameraPairingCode');
  for (const failure of ['network', 'unauthorized', 'bad_code']) {
    const e = environment();
    e.stored.set('smartshelf_pairing_code', 'stale-code');
    e.context.authFetch = async () => {
      if (failure === 'network') throw Error('network unavailable');
      return {ok: failure === 'bad_code', status: 401,
        json: async () => failure === 'bad_code' ? {pairing_code: 'fake'} : {detail: 'login required'}};
    };
    vm.runInContext(generate, e.context);
    await e.context.generateCameraPairingCode();
    assert.equal(e.stored.has('smartshelf_pairing_code'), false);
    assert.equal(e.element('pairingCodeDisplay').textContent, '');
    assert.equal(e.element('pairingCodeCard').style.display, 'none');
    assert.equal(e.context.toasts.at(-1).type, 'error');
  }
  const e = environment();
  e.context.authFetch = async () => ({ok: true, json: async () => ({pairing_code: '123456', expires_in: 300})});
  vm.runInContext(generate, e.context);
  await e.context.generateCameraPairingCode();
  assert.equal(e.element('pairingCodeDisplay').textContent, '123456');
  assert.equal(e.context.toasts.at(-1).type, 'success');
  console.log('PASS: real camera/admin handlers, localized code input, invalid-code rejection and no fabricated fallback');
})().catch(error => {console.error(error);process.exitCode = 1;});

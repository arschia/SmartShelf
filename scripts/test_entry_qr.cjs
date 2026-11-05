const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');const format=require(path.join(root,'frontend/assets/js/format.js'));
const sandbox={window:null,URL,SmartShelfFormat:format,location:{origin:'https://shelf-ir.vercel.app'}};sandbox.window=sandbox;
vm.runInNewContext(fs.readFileSync(path.join(root,'frontend/enter/qr.js'),'utf8'),sandbox);
const parse=sandbox.SmartShelfEntryQr.tokenFromInput;
for(const value of ['123456','۱۲۳۴۵۶','١٢٣٤٥٦','\u200f۱۲۳ ۴۵۶\u200e','https://shelf-ir.vercel.app/enter/?token=123456'])assert.equal(parse(value),'123456');
for(const value of ['https://foreign.invalid/enter/?token=123456','https://shelf-ir.vercel.app/admin?token=123456','123','wrong!'])assert.throws(()=>parse(value));
if(process.argv[2]){
  const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),jsQR=require(path.join(root,'frontend/assets/js/jsQR-1.4.0.js'));
  const result=jsQR(new Uint8ClampedArray(Buffer.from(fixture.data,'base64')),fixture.width,fixture.height);
  assert(result,'real QR pixels must decode');assert.equal(parse(result.data),'123456');
}
console.log('PASS: entry QR/code parser, Persian/Arabic digits, current-store URL validation'+(process.argv[2]?' and actual QR pixel decoding':'')+'.');

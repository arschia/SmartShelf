from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    required=['backend/app/routes/camera_transport.py','backend/app/main.py','backend/app/services/camera_pairing.py','frontend/camera/app.js','frontend/enter/qr.js','frontend/assets/js/jsQR-1.4.0.js']
    for name in required:
        path=ROOT/name
        if not path.is_file():
            print('MISSING:',name);return 1
        if path.suffix=='.py':compile(path.read_text(encoding='utf-8'),str(path),'exec')
    from backend.app.services.camera_pairing import _signed_device_token,get_device_info_by_token
    test=_signed_device_token('installation_check',time.time())
    if not get_device_info_by_token(test):
        print('PAIRING SIGNATURE CHECK FAILED');return 1
    print('CONNECTION UPDATE READY')
    print('Start/restart START-SMARTSHELF.bat, refresh the tablet page, and pair once with a NEW camera code.')
    print('Customer entry: https://frontend-rho-nine-46.vercel.app/ -> Customer entry -> Scan QR or enter the code above QR.')
    print('Activate/configure the university scenario at https://frontend-rho-nine-46.vercel.app/shop')
    return 0


if __name__=='__main__':
    raise SystemExit(main())

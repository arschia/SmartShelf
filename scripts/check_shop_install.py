"""Non-mutating Windows installation check. Startup performs backed-up DB migrations."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    required=['backend/app/routes/shop.py','backend/app/services/shop_scenario.py','frontend/shop.html','frontend/shop.js']
    for name in required:
        if not (ROOT/name).is_file():
            print('MISSING FILE:',name);return 1
    try:
        from backend.app.vision.bottle_detector import BottleDetector
        from backend.app.models import ShopScenario,Product
        from backend.app.routes.shop import router
        status=BottleDetector().status()
        if not status['ready']:
            print('MODEL NOT READY:',status['error']);return 1
        assert hasattr(Product,'stock_quantity')
        print('SHOP UPDATE READY')
        print('Model:',status['model'])
        print('Now start/restart START-SMARTSHELF.bat.')
        print('Startup automatically backs up and updates the SQLite schema.')
        print('Open https://frontend-rho-nine-46.vercel.app/shop and configure the university demo.')
        print('Existing PIN, Funnel URL and STORE_OPEN setting were not changed.')
        return 0
    except Exception as exc:
        print('UPDATE CHECK FAILED:',type(exc).__name__)
        print('Extract all update files inside your installed SmartShelf folder.');return 1


if __name__=='__main__':
    raise SystemExit(main())

"""Owner-run local verification of the portable ONNX model; no secrets displayed."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    try:
        from backend.app.vision.bottle_detector import BottleDetector
        import numpy as np
        detector = BottleDetector()
        info = detector.status()
        if not info['ready']:
            print('MODEL NOT READY:', info['error'])
            return 1
        result = detector.detect(np.zeros((480,640,3),dtype=np.uint8))
        print('MODEL READY:',info['model'])
        print('MODE:',info['mode'])
        print('CPU SELF-CHECK:',result['elapsed_ms'],'ms')
        print('This is a model load check, not an accuracy evaluation.')
        print('Restart backend: Ctrl+C in its old window, then START-SMARTSHELF.bat.')
        print('Open https://shelf-ir.vercel.app/bottle (Ctrl+F5 if needed).')
        return 0
    except Exception as exc:
        print('CHECK FAILED:',type(exc).__name__)
        print('Verify that this update was extracted into the installed SmartShelf folder.')
        return 1


if __name__=='__main__':
    raise SystemExit(main())

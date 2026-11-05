"""Read-only localhost check; never requests admin credentials or opens a port."""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent


def main():
    for name in ('backend/app/routes/rtc.py', 'frontend/assets/js/rtc.js'):
        if not (ROOT / name).is_file():
            print('MISSING: ' + name + '. Extract the update inside your installed SmartShelf folder.')
            return 1
    try:
        with urlopen('http://127.0.0.1:8000/api/health', timeout=5) as response:
            if json.load(response).get('status') != 'ok': raise ValueError('Backend health is not OK.')
        request = Request('http://127.0.0.1:8000/api/rtc/view', data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=5):
                print('ERROR: WebRTC viewer unexpectedly accepted a request without admin authentication.')
                return 1
        except HTTPError as error:
            if error.code != 401:
                print('WebRTC route is not ready (HTTP ' + str(error.code) + '). Restart the backend after extracting this update.')
                return 1
        print('PASS: backend healthy; WebRTC signaling installed and requires admin authentication.')
        print('Open the updated /camera/ page on the tablet, then use Show camera in /shop or Devices in /admin/.')
        print('Target: 720p / 30 FPS. Actual FPS depends on camera and network; it is shown in the viewer.')
        print('For the first test, connect tablet and viewing browser to the same Wi-Fi.')
        return 0
    except (URLError, ValueError, TimeoutError) as error:
        print('Backend is not ready: ' + str(error) + '. Start START-SMARTSHELF.bat first.')
        return 1


if __name__ == '__main__':
    sys.exit(main())

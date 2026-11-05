"""Offline source/package checks. Does not contact Railway/Vercel or start a camera."""
from pathlib import Path
import json
import compileall
import subprocess
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = [
    'README.md', '.env.example', '.gitignore', '.dockerignore', 'Dockerfile',
    'railway.json', 'requirements-cloud.txt', 'scripts/start_backend.sh',
    'frontend/vercel.json', 'frontend/config.js', 'frontend/presence.html',
    'backend/app/main.py', 'backend/app/vision/two_reference.py',
]


def main():
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    assert not missing, f'Missing files: {missing}'
    assert not (ROOT / '.env').exists(), 'Private .env must never be bundled'
    for extension in ('*.pem', '*.key', '*.db', '*.sqlite', '*.sqlite3'):
        assert not list(ROOT.rglob(extension)), f'Forbidden secret/data file: {extension}'
    railway = json.loads((ROOT / 'railway.json').read_text())
    assert railway['deploy']['numReplicas'] == 1, 'SQLite + in-memory WS requires one replica'
    assert json.loads((ROOT / 'frontend/vercel.json').read_text())
    assert compileall.compile_dir(str(ROOT / 'backend'), quiet=1)
    assert compileall.compile_dir(str(ROOT / 'scripts'), quiet=1)
    node = shutil.which('node')
    if node:
        for file in ('frontend/assets/js/api.js', 'frontend/admin/app.js', 'frontend/camera/app.js', 'frontend/customer/app.js'):
            subprocess.run([node, '--check', str(ROOT / file)], check=True)
    print('PASS: required files, no bundled secrets, single replica, JSON, Python, JS' + (' (Node checked)' if node else ' (Node unavailable)'))
    print('NOTE: this is NOT a live cloud build or tablet-camera test.')

if __name__ == '__main__':
    main()

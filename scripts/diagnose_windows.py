"""Allowlisted diagnostics: never exports PIN, tokens, raw logs, .env or images."""
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
from prepare_windows_env import parse
from verify_public_backend import collect_checks, https_origin

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ['fastapi', 'uvicorn', 'websockets', 'SQLAlchemy', 'pydantic',
            'opencv-python-headless', 'numpy', 'pillow', 'python-multipart', 'onnxruntime', 'zxing-cpp']


def run_json(command):
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=12, check=False)
        if proc.returncode == 0:
            return json.loads(proc.stdout.lstrip('\ufeff'))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def windows_state():
    if os.name != 'nt':
        return {'status': 'NOT_TESTED_ON_WINDOWS'}
    script = "$l=@(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue);" \
             "$bad=@($l|Where-Object {$_.LocalAddress -notin @('127.0.0.1','::1')});" \
             "$t=Get-ScheduledTask -TaskName 'SmartShelf Backend' -ErrorAction SilentlyContinue;" \
             "@{port_listening=([bool]$l.Count);loopback_only=($l.Count -gt 0 -and $bad.Count -eq 0);" \
             "autostart_registered=([bool]$t)}|ConvertTo-Json -Compress"
    return run_json(['powershell.exe', '-NoProfile', '-Command', script]) or {'status': 'UNAVAILABLE'}


def tailscale_state():
    ts = shutil.which('tailscale')
    if not ts:
        for base in [os.getenv('ProgramFiles', ''), os.getenv('ProgramFiles(x86)', '')]:
            for folder in ['Tailscale', 'Tailscale IPN']:
                candidate = Path(base) / folder / 'tailscale.exe'
                if candidate.is_file():
                    ts = str(candidate)
                    break
    if not ts:
        return {'installed': False, 'running': False, 'funnel_configured': False}
    status = run_json([ts, 'status', '--json']) or {}
    funnel = run_json([ts, 'funnel', 'status', '--json']) or {}
    return {'installed': True, 'running': status.get('BackendState') == 'Running',
            'funnel_configured': any((funnel.get('AllowFunnel') or {}).values())}


def collect_report(root=ROOT, offline=False):
    env = root / '.env'
    values = parse(env.read_text(encoding='utf-8-sig').splitlines()) if env.exists() else {}
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = 'MISSING'
    frontend = 'https://frontend-rho-nine-46.vercel.app'
    backend = None
    try:
        candidate = https_origin(values.get('PUBLIC_BASE_URL', ''))
        if urlsplit(candidate).hostname.endswith('.ts.net'):
            backend = candidate
    except ValueError:
        pass
    return {
        'release': 'windows-local-1.1',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'runtime': {'os': platform.system(), 'python': platform.python_version(), 'bits': struct.calcsize('P') * 8},
        'packages': versions,
        'configuration': {
            'env_exists': env.exists(),
            'production_configured': values.get('APP_ENV') == 'production',
            'store_closed_configured': values.get('STORE_OPEN', '').lower() == 'false',
            'admin_pin_configured': len(values.get('ADMIN_PIN', '')) >= 8,
            'secret_key_configured': len(values.get('SECRET_KEY', '')) >= 32,
            'identity_model_disabled': values.get('RECOGNITION_MODEL_PATH', '').endswith('identity-disabled-until-validated.onnx'),
            'frontend_origin_allowed': frontend in values.get('ALLOWED_ORIGINS', '').split(','),
            'frontend_url': frontend, 'public_backend_url': backend,
        },
        'storage': {'database_exists': (root / 'data' / 'smartshelf.db').is_file(),
                    'upload_directory_exists': (root / 'data' / 'uploads').is_dir()},
        'windows': windows_state() if not offline else {'status': 'SKIPPED_OFFLINE'},
        'tailscale': tailscale_state() if not offline else {'status': 'SKIPPED_OFFLINE'},
        'local_checks': collect_checks('http://127.0.0.1:8000', frontend) if not offline else [],
        'public_checks': collect_checks(backend, frontend) if backend and not offline else [],
        'remaining_manual_checks': ['Restart backend after configuring Funnel URL',
            'Tablet pairing and sustained camera streaming', 'Two-reference calibration in real lighting',
            'Database persistence after Windows sign-in', 'Keep store closed until physical tests pass'],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true', help='Skip network and OS commands')
    args = parser.parse_args()
    report = collect_report(offline=args.offline)
    output = ROOT / 'logs' / 'diagnostics-latest.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for scope in ['local_checks', 'public_checks']:
        for check in report[scope]:
            print(check['status'] + '  ' + scope + '  ' + check['check'])
    print('Report saved: logs\\diagnostics-latest.json')
    print('Send ONLY this report or the public .ts.net URL; do not send .env, PIN, raw logs or backups.')
    checks = report['local_checks'] + report['public_checks']
    ready = (bool(report['local_checks']) and bool(report['public_checks'])
        and all(c['status'] == 'PASS' for c in checks)
        and report['configuration']['store_closed_configured']
        and report['windows'].get('loopback_only') is True
        and report['tailscale'].get('running') is True
        and report['tailscale'].get('funnel_configured') is True
        and all(v != 'MISSING' for v in report['packages'].values()))
    print('Connectivity checks complete; physical camera tests pending.' if ready else 'Setup needs attention; send the diagnostic report to continue.')
    return 0 if ready else 1


if __name__ == '__main__':
    sys.exit(main())

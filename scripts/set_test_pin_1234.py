"""Explicit owner-run reset to PIN 1234 for closed-store testing only."""
from pathlib import Path
from datetime import datetime
import os
import shutil
from prepare_windows_env import parse, set_value

ROOT = Path(__file__).resolve().parent.parent


def configure(root=ROOT):
    env = root / '.env'
    config = root / 'backend' / 'app' / 'config.py'
    if not env.is_file() or not config.is_file():
        raise ValueError('Extract this patch into the installed SmartShelf folder first.')
    if 'ALLOW_INSECURE_TEST_PIN' not in config.read_text(encoding='utf-8-sig'):
        raise ValueError('The backend config update from this patch is missing.')
    text = env.read_text(encoding='utf-8-sig')
    lines = text.splitlines()
    previous = parse(lines)
    if previous.get('APP_ENV') != 'production':
        raise ValueError('Expected the Windows production configuration.')
    for key, value in {'ADMIN_PIN': '1234', 'ALLOW_INSECURE_TEST_PIN': 'true', 'STORE_OPEN': 'false'}.items():
        lines = set_value(lines, key, value)
    new_values = parse(lines)
    for key in set(previous) - {'ADMIN_PIN', 'ALLOW_INSECURE_TEST_PIN', 'STORE_OPEN'}:
        if new_values.get(key) != previous[key]:
            raise ValueError('Unrelated configuration changed; reset was cancelled.')
    # Keep a private rollback copy on this computer, never inside the patch ZIP.
    backups = root / 'backups'
    backups.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    shutil.copy2(env, backups / ('.env-before-pin-reset-' + stamp + '.bak'))
    temp = env.with_name('.env.pin-update.tmp')
    try:
        temp.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
        os.replace(temp, env)
    finally:
        temp.unlink(missing_ok=True)


def main():
    try:
        configure()
    except (OSError, ValueError) as exc:
        print('PIN RESET FAILED:', str(exc))
        return 1
    print('PIN UPDATED: 1234')
    print('STORE_OPEN=false; this is an explicitly enabled insecure test PIN.')
    print('Restart the backend now: Ctrl+C, then option 3 in SmartShelf Control.')
    print('The old failed-login counter is in memory and resets with the backend restart.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

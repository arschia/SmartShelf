"""Allow this project's exact Vercel Preview origin for the existing Windows backend."""
from pathlib import Path
import json
import os
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
BACKEND = 'https://your-device.your-tailnet.ts.net'
FRONTEND = 'https://shelf-ir.vercel.app'
PREVIEW = 'https://shelf-np1iagre5-arschias-projects.vercel.app'


def configure(root=ROOT):
    env = root / '.env'
    if not env.is_file():
        raise ValueError('Run this patch inside the installed SmartShelf folder; .env was not found.')
    text = env.read_text(encoding='utf-8-sig')
    # Dotenv updates are restricted to literal deployment values. Private fields
    # and every other line are copied verbatim and are never printed.
    def value(key):
        match = re.search(r'^\s*' + re.escape(key) + r'\s*=\s*(.*?)\s*$', text, re.MULTILINE)
        return match.group(1).strip().strip('\"\'') if match else ''

    if value('APP_ENV') != 'production':
        raise ValueError('Expected the production configuration produced by the Windows installer.')
    if value('PUBLIC_BASE_URL').rstrip('/') != BACKEND:
        raise ValueError('The configured Funnel URL differs from the verified backend. Rerun Funnel setup first.')
    origins = [s.strip() for s in value('ALLOWED_ORIGINS').split(',') if s.strip()]
    if '*' in origins:
        raise ValueError('Wildcard CORS must be reviewed before this exact-origin patch can run.')
    for origin in [FRONTEND, PREVIEW]:
        if origin not in origins:
            origins.append(origin)
    updates = {'ALLOWED_ORIGINS': ','.join(origins), 'PUBLIC_BASE_URL': BACKEND,
               'FRONTEND_PUBLIC_URL': FRONTEND, 'STORE_OPEN': 'false'}
    lines = text.splitlines()
    for key, new_value in updates.items():
        pattern = re.compile(r'^\s*' + re.escape(key) + r'\s*=')
        found = False
        output = []
        for line in lines:
            if pattern.match(line):
                if not found:
                    output.append(key + '=' + new_value)
                    found = True
            else:
                output.append(line)
        if not found:
            output.append(key + '=' + new_value)
        lines = output
    new_text = '\n'.join(lines).rstrip() + '\n'
    # This patch has no permission to change authentication credentials.
    for key in ('ADMIN_PIN', 'SECRET_KEY'):
        pattern = re.compile(r'^\s*' + key + r'\s*=.*$', re.MULTILINE)
        if pattern.findall(new_text) != pattern.findall(text):
            raise ValueError('Credential preservation check failed; no changes were written.')
    temporary = env.with_name('.env.preview-update.tmp')
    try:
        temporary.write_text(new_text, encoding='utf-8')
        os.replace(temporary, env)
    finally:
        temporary.unlink(missing_ok=True)
    # The already-deployed Preview uses this same public backend origin.
    config = root / 'frontend' / 'config.js'
    if config.parent.is_dir():
        config.write_text('window.SMARTSHELF_CONFIG = ' + json.dumps({'apiBase': BACKEND}) + ';\n', encoding='utf-8')


def main():
    try:
        configure()
    except (OSError, ValueError) as exc:
        print('SETUP FAILED:', str(exc))
        return 1
    print('PREVIEW CONFIGURED.')
    print('Restart the backend: Ctrl+C in its window, then choose option 3 in SmartShelf Control.')
    print('After restart open:', PREVIEW + '/admin/')
    print('STORE_OPEN=false. Admin credentials were preserved and are not displayed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

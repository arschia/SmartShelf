"""
Phase 9 Deployment & Tunnel Verification Tests for SMARTSHELF
Verifies static configuration for Vercel, pre-deployment secret scanning,
tunnel launcher script, CORS/TrustProxy handling, and demo mode.
"""
import json
import subprocess
import sys
import shutil
from pathlib import Path
import pytest

from backend.app.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
VERCEL_JSON = FRONTEND_DIR / "vercel.json"
PREDEPLOY_SCRIPT = PROJECT_ROOT / "scripts" / "predeploy_check.py"
TUNNEL_SCRIPT = PROJECT_ROOT / "scripts" / "start_tunnel.bat"


def _predeploy_copy(tmp_path):
    # Test an isolated deployment, never the owner's private .env or frontend config.
    for folder in ('frontend', 'backend', 'scripts'):
        shutil.copytree(PROJECT_ROOT / folder, tmp_path / folder,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(PROJECT_ROOT / '.gitignore', tmp_path / '.gitignore')
    return tmp_path


def test_predeploy_check_script_passes(tmp_path):
    """A complete isolated production configuration passes the static release gate."""
    root = _predeploy_copy(tmp_path)
    backend = 'https://qa-shelf.testnet.ts.net'
    (root / '.env').write_text('\n'.join([
        'APP_ENV=production', 'ADMIN_PIN=TestDeploymentPin-2026',
        'SECRET_KEY=test-only-deployment-secret-not-for-production-2026',
        'FRONTEND_PUBLIC_URL=https://shelf-ir.vercel.app',
        'ALLOWED_ORIGINS=https://shelf-ir.vercel.app',
        'STORE_OPEN=false', f'PUBLIC_BASE_URL={backend}',
    ]), encoding='utf-8')
    (root / 'frontend' / 'config.js').write_text(
        'window.SMARTSHELF_CONFIG = {apiBase: ' + json.dumps(backend) + '};', encoding='utf-8')
    res = subprocess.run(
        [sys.executable, str(root / 'scripts' / 'predeploy_check.py')],
        capture_output=True,
        text=True,
        cwd=str(root)
    )
    assert res.returncode == 0, f"predeploy_check.py failed:\n{res.stdout}\n{res.stderr}"
    assert "ALL PRE-DEPLOYMENT CHECKS PASSED" in res.stdout


def test_predeploy_blocks_unconfigured_windows_package(tmp_path):
    root = _predeploy_copy(tmp_path)
    res = subprocess.run([sys.executable, str(root / 'scripts' / 'predeploy_check.py')],
                         capture_output=True, text=True, cwd=root)
    assert res.returncode == 1
    assert '.env is not present' in res.stdout


def test_backend_config_trust_proxy_and_frontend_public_url():
    """Verify Settings class correctly parses TRUST_PROXY and includes FRONTEND_PUBLIC_URL in ALLOWED_ORIGINS."""
    cfg = Settings(
        TRUST_PROXY="true",
        ALLOWED_ORIGINS_RAW="http://localhost:8000",
        FRONTEND_PUBLIC_URL="https://smartshelf-test.vercel.app/"
    )
    assert cfg.TRUST_PROXY is True
    assert "https://smartshelf-test.vercel.app" in cfg.ALLOWED_ORIGINS
    assert "http://localhost:8000" in cfg.ALLOWED_ORIGINS


def test_vercel_json_rewrites_and_security_headers():
    """Verify frontend/vercel.json is valid and contains routing rewrites and security headers."""
    assert VERCEL_JSON.exists(), "frontend/vercel.json must exist"
    data = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))

    assert data.get("cleanUrls") is True

    # Check key route rewrites
    sources = [r["source"] for r in data.get("rewrites", [])]
    assert "/admin" in sources
    assert "/customer" in sources
    assert "/camera" in sources
    assert "/demo" in sources
    assert "/enter" in sources

    # Check headers
    headers_config = data.get("headers", [])
    assert len(headers_config) > 0
    all_header_keys = [h["key"] for item in headers_config for h in item.get("headers", [])]
    assert "X-Content-Type-Options" in all_header_keys
    assert "X-Frame-Options" in all_header_keys


def test_frontend_has_zero_serverless_functions_and_zero_private_keys():
    """Verify there are no serverless functions in frontend/ (zero frame storage on Vercel)."""
    api_dir = FRONTEND_DIR / "api"
    assert not api_dir.exists(), "frontend/api must not exist (no serverless functions)"

    # Verify no .pem or .key files in frontend
    sensitive_files = list(FRONTEND_DIR.glob("**/*.pem")) + list(FRONTEND_DIR.glob("**/*.key"))
    assert len(sensitive_files) == 0, f"Found sensitive keys in frontend: {sensitive_files}"


def test_tunnel_launcher_script_exists():
    """Verify the selected Windows tunnel launcher routes only to Tailscale Funnel."""
    assert TUNNEL_SCRIPT.exists(), "scripts/start_tunnel.bat must exist"
    content = TUNNEL_SCRIPT.read_text(encoding="utf-8")
    assert "tailscale" in content.lower()
    assert "ENABLE-FUNNEL.bat" in content
    assert "cloudflared" not in content.lower()


def test_landing_page_has_demo_cta_and_limitations():
    """Verify frontend/index.html highlights the standalone demo simulator and honest limitations."""
    index_file = FRONTEND_DIR / "index.html"
    assert index_file.exists()
    html = index_file.read_text(encoding="utf-8")

    assert "/demo/" in html
    assert "امتحان کنید" in html or "شبیه‌ساز" in html
    assert "محدودیت‌های" in html or "توضیح صادقانه" in html
    assert "portalStatusDot" in html

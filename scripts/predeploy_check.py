#!/usr/bin/env python3
"""
SMARTSHELF Pre-Deployment Verification Script
Ensures no secrets (PIN, SECRET_KEY, private keys, database files) exist in the frontend,
verifies .gitignore rules, and confirms no serverless functions exist on Vercel.
"""
import os
import re
import sys
from pathlib import Path
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
GITIGNORE_FILE = PROJECT_ROOT / ".gitignore"
ENV_FILE = PROJECT_ROOT / ".env"

FORBIDDEN_EXTENSIONS = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".bak", ".env"}
FORBIDDEN_NAMES = {"smartshelf.db", ".env", "cert.pem", "key.pem", "smartshelf.db.bak"}

SECRET_REGEXES = [
    (re.compile(r"-----BEGIN[ A-Z0-9_-]*PRIVATE KEY-----"), "Private key block detected"),
    (re.compile(r"ADMIN_PIN\s*[:=]\s*['\"][^'\"]{4,}['\"]", re.IGNORECASE), "Admin PIN hardcoded assignment"),
    (re.compile(r"SECRET_KEY\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]", re.IGNORECASE), "Secret Key hardcoded assignment"),
    (re.compile(r"Bearer\s+ey[a-zA-Z0-9_\-]+\.ey[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+"), "JWT Token hardcoded in frontend"),
]


def check_secrets_in_frontend() -> bool:
    print("[1/7] Scanning frontend directory for leaked secrets...")
    failed = False

    # Load actual values from .env if present
    env_secrets = {}
    if ENV_FILE.exists():
        env_vals = dotenv_values(ENV_FILE)
        if env_vals.get("ADMIN_PIN") and len(env_vals["ADMIN_PIN"]) >= 8:
            env_secrets["ADMIN_PIN"] = env_vals["ADMIN_PIN"]
        if env_vals.get("SECRET_KEY") and len(env_vals["SECRET_KEY"]) >= 16:
            env_secrets["SECRET_KEY"] = env_vals["SECRET_KEY"]

    text_extensions = {".html", ".js", ".json", ".css", ".md", ".txt"}

    for root, _, files in os.walk(FRONTEND_DIR):
        for f in files:
            p = Path(root) / f
            rel = p.relative_to(PROJECT_ROOT)

            # Check forbidden extensions / file names
            if p.suffix.lower() in FORBIDDEN_EXTENSIONS or f.lower() in FORBIDDEN_NAMES:
                print(f"  [FAIL] Forbidden sensitive file found in frontend: {rel}")
                failed = True
                continue

            if p.suffix.lower() in text_extensions:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    print(f"  [WARN] Could not read {rel}: {e}")
                    continue

                # Check regexes
                for rx, desc in SECRET_REGEXES:
                    if rx.search(content):
                        print(f"  [FAIL] {desc} in {rel}")
                        failed = True

                # Check verbatim values from .env
                for secret_name, secret_val in env_secrets.items():
                    if secret_val in content:
                        print(f"  [FAIL] Real .env value of {secret_name} found in {rel}!")
                        failed = True

    if not failed:
        print("  [PASS] Zero secrets or sensitive keys found in frontend directory.")
    return not failed


def check_gitignore() -> bool:
    print("[2/7] Verifying .gitignore rules...")
    if not GITIGNORE_FILE.exists():
        print("  [FAIL] .gitignore file does not exist!")
        return False

    content = GITIGNORE_FILE.read_text(encoding="utf-8")
    required_entries = [".env", "*.pem", "*.db", "*.bak"]
    missing = []
    for req in required_entries:
        if req not in content:
            missing.append(req)

    if missing:
        print(f"  [FAIL] .gitignore missing required entries: {missing}")
        return False

    print("  [PASS] .gitignore correctly ignores .env, *.pem, *.db, and *.bak.")
    return True


def check_no_serverless_functions() -> bool:
    print("[3/7] Verifying no serverless functions on Vercel (zero frame retention)...")
    api_dir = FRONTEND_DIR / "api"
    if api_dir.exists() and api_dir.is_dir():
        py_or_js = list(api_dir.glob("*.js")) + list(api_dir.glob("*.py")) + list(api_dir.glob("*.ts"))
        if py_or_js:
            print(f"  [FAIL] Serverless functions found in frontend/api: {py_or_js}")
            return False

    print("  [PASS] No serverless functions found in frontend/ (100% static hosting on Vercel).")
    return True


def check_frontend_config() -> bool:
    print("[4/7] Verifying frontend/config.js integrity...")
    config_file = FRONTEND_DIR / "config.js"
    if not config_file.exists():
        print("  [FAIL] frontend/config.js is missing!")
        return False

    content = config_file.read_text(encoding="utf-8")
    if "admin" in content.lower() and "pin" in content.lower():
        print("  [FAIL] Sensitive admin/pin keyword found in config.js!")
        return False

    print("  [PASS] frontend/config.js is safe and free of secrets.")
    return True


def check_no_public_relays_or_mock_auth() -> bool:
    print("[5/7] Checking production frontend for public relays and simulated auth...")
    forbidden = {
        "https://ntfy.sh": "Public ntfy relay",
        "new Peer(": "Unauthenticated third-party P2P signaling",
        "handleStandaloneAdminMock": "Standalone mock admin authentication",
        "vcl_dev_": "Fake camera device token",
        "smartshelf_live_cart_events": "Public cart event channel",
        "sec_vcl_": "Fake customer session token",
        "standaloneSecret": "Standalone simulated customer session",
        "vcl_admin_": "Fake admin session token",
    }
    failed = False
    for root, _, files in os.walk(FRONTEND_DIR):
        for filename in files:
            path = Path(root) / filename
            if path.suffix.lower() not in {".js", ".html", ".json"}:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            for marker, description in forbidden.items():
                if marker in content:
                    print(f"  [FAIL] {description} found in {path.relative_to(PROJECT_ROOT)}")
                    failed = True
    if not failed:
        print("  [PASS] No public event relays, P2P fallback, or mock authentication in frontend.")
    return not failed


def check_presence_integration() -> bool:
    print("[6/7] Checking two-reference presence integration...")
    required = [
        FRONTEND_DIR / "presence.html",
        PROJECT_ROOT / "backend" / "app" / "routes" / "presence.py",
        PROJECT_ROOT / "backend" / "app" / "vision" / "two_reference.py",
    ]
    missing = [str(p.relative_to(PROJECT_ROOT)) for p in required if not p.exists()]
    if missing:
        print(f"  [FAIL] Missing integration files: {missing}")
        return False
    main_file = (PROJECT_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    pipeline_file = (PROJECT_ROOT / "backend" / "app" / "vision" / "pipeline.py").read_text(encoding="utf-8")
    if "presence_router" not in main_file or "classify_two_reference" not in pipeline_file:
        print("  [FAIL] Presence API or vision pipeline is not connected.")
        return False
    print("  [PASS] Presence UI, authenticated API, and live vision pipeline are connected.")
    return True


def check_backend_runtime_config() -> bool:
    print("[7/7] Checking backend production configuration without revealing secrets...")
    if not ENV_FILE.exists():
        print("  [FAIL] .env is not present. Copy .env.example, generate secrets, and configure the HTTPS backend tunnel.")
        return False

    values = dotenv_values(ENV_FILE)
    failed = False
    pin = str(values.get("ADMIN_PIN") or "").strip()
    secret = str(values.get("SECRET_KEY") or "").strip()
    ttl = str(values.get("TOKEN_TTL_SECONDS") or "28800").strip()
    frontend = str(values.get("FRONTEND_PUBLIC_URL") or "").strip().rstrip("/")
    origins = str(values.get("ALLOWED_ORIGINS") or "")
    backend = str(values.get("PUBLIC_BASE_URL") or "").strip()
    store_open = str(values.get("STORE_OPEN") or "false").strip().lower() == "true"
    app_env = str(values.get("APP_ENV") or "production").strip().lower()
    config_js = (FRONTEND_DIR / "config.js").read_text(encoding="utf-8")
    api_match = re.search(r'apiBase\s*:\s*["\']([^"\']*)["\']', config_js)
    api_base = api_match.group(1).strip().rstrip("/") if api_match else ""

    if app_env != "production":
        print("  [FAIL] APP_ENV must be production for public release.")
        failed = True
    if len(pin) < 8 or pin == "1234" or pin.lower().startswith("change-me"):
        print("  [FAIL] ADMIN_PIN must be a unique value with at least 8 characters.")
        failed = True
    if len(secret) < 32 or secret.lower().startswith("change-me"):
        print("  [FAIL] SECRET_KEY must be a random value of at least 32 characters.")
        failed = True
    try:
        ttl_value = int(ttl)
        if ttl_value < 60 or ttl_value > 86400:
            raise ValueError()
    except ValueError:
        print("  [FAIL] TOKEN_TTL_SECONDS must be between 60 and 86400.")
        failed = True
    if frontend != "https://frontend-rho-nine-46.vercel.app":
        print("  [FAIL] FRONTEND_PUBLIC_URL must be https://frontend-rho-nine-46.vercel.app.")
        failed = True
    if "https://frontend-rho-nine-46.vercel.app" not in origins:
        print("  [FAIL] ALLOWED_ORIGINS must include https://frontend-rho-nine-46.vercel.app.")
        failed = True
    if not backend.startswith("https://") or "localhost" in backend or ".example" in backend:
        print("  [FAIL] PUBLIC_BASE_URL must be the actual HTTPS tunnel URL for FastAPI.")
        failed = True
    if not api_base.startswith("https://") or "localhost" in api_base or ".example" in api_base:
        print("  [FAIL] frontend/config.js apiBase must contain the same public HTTPS backend URL.")
        failed = True
    if backend.rstrip("/") != api_base:
        print("  [FAIL] PUBLIC_BASE_URL and frontend/config.js apiBase must point to the same backend.")
        failed = True

    if store_open:
        print("  [WARN] STORE_OPEN=true: customer entry is enabled; verify real tablet and product-identity accuracy before accepting purchases.")
    else:
        print("  [INFO] STORE_OPEN=false: customer entry remains safely closed until launch approval.")

    if failed:
        print("  [WARN] Public backend launch is blocked until these settings are corrected.")
        return False
    print("  [PASS] Backend secret strength, token lifetime, frontend CORS, and HTTPS tunnel settings are configured.")
    return True


def main():
    print("=" * 60)
    print("  SMARTSHELF PRE-DEPLOYMENT VERIFICATION CHECK")
    print("=" * 60)

    ok1 = check_secrets_in_frontend()
    ok2 = check_gitignore()
    ok3 = check_no_serverless_functions()
    ok4 = check_frontend_config()
    ok5 = check_no_public_relays_or_mock_auth()
    ok6 = check_presence_integration()
    ok7 = check_backend_runtime_config()

    print("=" * 60)
    if ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7:
        print("  RESULT: ALL PRE-DEPLOYMENT CHECKS PASSED [READY FOR VERCEL]")
        print("=" * 60)
        sys.exit(0)
    else:
        print("  RESULT: PRE-DEPLOYMENT CHECKS FAILED! DO NOT DEPLOY.")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()

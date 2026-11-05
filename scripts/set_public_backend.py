"""Set the real Tailscale Funnel origin in the private backend config and local frontend config."""
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent


def set_env(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    prefix = key + "="
    out, found = [], False
    for line in lines:
        if line.lstrip().startswith(prefix):
            if not found:
                out.append(prefix + value)
                found = True
        else:
            out.append(line)
    if not found:
        out.append(prefix + value)
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/set_public_backend.py https://device.tailnet.ts.net")
    url = sys.argv[1].strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".ts.net") or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise SystemExit("Expected the exact HTTPS Tailscale Funnel origin, e.g. https://device.tailnet.ts.net")
    env = ROOT / ".env"
    if not env.exists():
        raise SystemExit(".env is missing; run scripts/prepare_windows_env.py first")
    set_env(env, "PUBLIC_BASE_URL", url)
    set_env(env, "FRONTEND_PUBLIC_URL", "https://shelf-ir.vercel.app")
    set_env(env, "ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,https://shelf-ir.vercel.app")
    set_env(env, "STORE_OPEN", "false")
    set_env(env, "TRUST_PROXY", "false")
    config = ROOT / "frontend" / "config.js"
    # JSON-compatible JS string literal (URLs contain no quotes, but escape defensively).
    js = "// Public backend origin only; never put secrets here.\nwindow.SMARTSHELF_CONFIG = { apiBase: \"" + url.replace("\\", "\\\\").replace('"', '\\"') + "\" };\n"
    config.write_text(js, encoding="utf-8")
    print("[OK] PUBLIC_BASE_URL updated in private .env")
    print("[OK] frontend/config.js updated in local source")
    print("[OK] STORE_OPEN is forced to false")
    print("Backend origin:", url)


if __name__ == "__main__":
    main()

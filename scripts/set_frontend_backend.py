"""Set public backend origin in frontend/config.js. No credentials are written."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent

def normalize(url):
    u = urlsplit(url.strip())
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.path not in ("", "/") or u.query or u.fragment:
        raise ValueError("Expected an HTTPS origin only, e.g. https://your-backend.up.railway.app")
    return u.geturl().rstrip("/")

def main():
    parser = argparse.ArgumentParser(description="Configure Vercel frontend backend origin")
    parser.add_argument("url", help="Public HTTPS origin of the persistent FastAPI backend")
    args = parser.parse_args()
    origin = normalize(args.url)
    config = ROOT / "frontend" / "config.js"
    config.write_text("// Public backend origin only; never put secrets here.\nwindow.SMARTSHELF_CONFIG = { apiBase: " + json.dumps(origin) + " };\n", encoding="utf-8")
    print("Frontend API origin set:", origin)
    print("Deploy frontend/ to Vercel preview first. No production change was made.")

if __name__ == "__main__":
    main()

"""Script to audit and verify that all referenced root-relative asset paths in the frontend exist on disk."""
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

ASSET_REGEX = re.compile(r"""(?:href|src|url)\s*[:=\(]\s*['"]?(/assets/[^'"\)\s,]+|/static/[^'"\)\s,]+|/config\.js)""", re.IGNORECASE)


def check_frontend_assets():
    print("=" * 60)
    print("  SMARTSHELF Frontend Assets Path Integrity Check")
    print("=" * 60)
    print(f"Scanning directory: {FRONTEND_DIR}")

    files_scanned = 0
    references_found = 0
    missing_assets = []
    found_assets = set()

    frontend_files = list(FRONTEND_DIR.rglob("*.html")) + list(FRONTEND_DIR.rglob("*.js")) + list(FRONTEND_DIR.rglob("*.css"))

    for fpath in frontend_files:
        files_scanned += 1
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"Warning: could not read {fpath.name}: {e}")
            continue

        for match in ASSET_REGEX.finditer(content):
            raw_path = match.group(1).split("?")[0].split("#")[0].strip()
            references_found += 1
            found_assets.add(raw_path)

            # Map root relative path (e.g. /assets/fonts/dana.css) to frontend/assets/fonts/dana.css
            disk_path = FRONTEND_DIR / raw_path.lstrip("/")
            if not disk_path.exists():
                missing_assets.append((fpath.relative_to(PROJECT_ROOT), raw_path, disk_path))

    print(f"\nScanned {files_scanned} frontend files.")
    print(f"Discovered {len(found_assets)} unique root-relative asset paths ({references_found} total references).\n")

    for asset in sorted(found_assets):
        target = FRONTEND_DIR / asset.lstrip("/")
        status = "OK" if target.exists() else "MISSING"
        symbol = "OK" if target.exists() else "FAIL"
        print(f"  [{symbol}] {asset} -> {status}")

    if missing_assets:
        print("\n" + "!" * 60)
        print("  ERROR: The following referenced assets are missing on disk:")
        print("!" * 60)
        for src_file, asset, disk in missing_assets:
            print(f"  - In {src_file}: {asset} (expected at {disk})")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  ALL REFERENCED ASSET PATHS EXIST! INTEGRITY VERIFIED (0 MISSING)")
    print("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    check_frontend_assets()

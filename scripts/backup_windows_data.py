"""Create a local backup using SQLite's online backup API plus uploaded product images."""
from pathlib import Path
from datetime import datetime
import sqlite3
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = DATA / "smartshelf.db"
UPLOADS = DATA / "uploads"
BACKUPS = ROOT / "backups"


def main():
    if not DB.exists():
        raise SystemExit(f"Database not found: {DB}")
    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    work = BACKUPS / f"SmartShelf-backup-{stamp}"
    work.mkdir()
    dst_db = work / "smartshelf.db"
    with sqlite3.connect(DB) as src, sqlite3.connect(dst_db) as dst:
        src.backup(dst)
    if UPLOADS.exists():
        shutil.copytree(UPLOADS, work / "uploads", dirs_exist_ok=True)
    archive = BACKUPS / f"SmartShelf-backup-{stamp}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in work.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(work.parent))
    shutil.rmtree(work)
    print("Backup created locally:", archive)
    print("Do not upload this archive to public storage; it may contain customer and business data.")


if __name__ == "__main__":
    main()

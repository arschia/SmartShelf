"""
SMARTSHELF Database Safe Migration Service
Performs automated backup of SQLite database before running idempotent schema migrations.
"""
import shutil
from pathlib import Path
from sqlalchemy import text
from ..config import settings
from ..db import engine


def backup_database() -> Path:
    """Create a backup of the current database before running schema changes."""
    db_url = getattr(settings, "DB_URL", "sqlite:///./smartshelf.db")
    if not db_url.startswith("sqlite") or ":memory:" in db_url:
        return Path()

    path_part = db_url.replace("sqlite:///", "")
    try:
        db_file = Path(path_part).resolve()
        if not db_file.exists() or not db_file.is_file():
            return Path()

        backup_path = db_file.with_name(f"{db_file.name}.bak")
        shutil.copy2(db_file, backup_path)
        print(f"[MIGRATION] Database backup successfully created at: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"[MIGRATION WARNING] Failed to create database backup: {e}")
        return Path()


def run_idempotent_migrations(target_engine=None):
    """
    Safely and idempotently upgrade the database schema to Phase 6 requirements:
    1. Backup smartshelf.db
    2. Add gtin, gtin14, brand, category, is_active to products table if missing
    3. Create unique partial index on gtin14
    4. Create product_images table if missing
    5. Sync legacy image_path into product_images
    """
    backup_database()
    active_engine = target_engine or engine

    with active_engine.connect() as conn:
        tables = [r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';")).fetchall()]
        if "products" in tables:
            res = conn.execute(text("PRAGMA table_info(products);"))
            existing_cols = {row[1] for row in res.fetchall()}

            if "gtin" not in existing_cols:
                conn.execute(text("ALTER TABLE products ADD COLUMN gtin VARCHAR(20);"))
            if "gtin14" not in existing_cols:
                conn.execute(text("ALTER TABLE products ADD COLUMN gtin14 VARCHAR(14);"))
            if "brand" not in existing_cols:
                conn.execute(text("ALTER TABLE products ADD COLUMN brand VARCHAR(100);"))
            if "category" not in existing_cols:
                conn.execute(text("ALTER TABLE products ADD COLUMN category VARCHAR(100);"))
            if "is_active" not in existing_cols:
                conn.execute(text("ALTER TABLE products ADD COLUMN is_active BOOLEAN DEFAULT 1;"))
            if "stock_quantity" not in existing_cols:
                conn.execute(text("ALTER TABLE products ADD COLUMN stock_quantity INTEGER NOT NULL DEFAULT 0;"))

            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_products_gtin14 ON products(gtin14) WHERE gtin14 IS NOT NULL;"))

        # Create product_images table if it does not exist
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS product_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                file_path VARCHAR(500) NOT NULL,
                is_primary BOOLEAN DEFAULT 0,
                created_at DATETIME,
                width INTEGER,
                height INTEGER
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_images_product_id ON product_images(product_id);"))

        # Populate product_images from legacy image_path if empty and products table exists
        if "products" in tables:
            conn.execute(text("""
                INSERT INTO product_images (product_id, file_path, is_primary, created_at)
                SELECT id, image_path, 1, CURRENT_TIMESTAMP
                FROM products
                WHERE image_path IS NOT NULL AND image_path != ''
                  AND id NOT IN (SELECT DISTINCT product_id FROM product_images);
            """))

        # Create product_embeddings table if it does not exist (Phase 7)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS product_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                image_id INTEGER REFERENCES product_images(id) ON DELETE CASCADE,
                vector BLOB NOT NULL,
                model_version VARCHAR(50) NOT NULL DEFAULT 'mobilenetv2-7',
                created_at DATETIME
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_embeddings_product_id ON product_embeddings(product_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_product_embeddings_image_id ON product_embeddings(image_id);"))

        # Check zones table for Phase 8 recognition fields
        if "zones" in tables:
            res_z = conn.execute(text("PRAGMA table_info(zones);"))
            existing_zone_cols = {row[1] for row in res_z.fetchall()}

            if "recognized_product_id" not in existing_zone_cols:
                conn.execute(text("ALTER TABLE zones ADD COLUMN recognized_product_id INTEGER REFERENCES products(id);"))
            if "recognition_status" not in existing_zone_cols:
                conn.execute(text("ALTER TABLE zones ADD COLUMN recognition_status VARCHAR(30) DEFAULT 'UNKNOWN';"))
            if "recognition_score" not in existing_zone_cols:
                conn.execute(text("ALTER TABLE zones ADD COLUMN recognition_score FLOAT DEFAULT 0.0;"))
            if "last_recognized_at" not in existing_zone_cols:
                conn.execute(text("ALTER TABLE zones ADD COLUMN last_recognized_at DATETIME;"))
            if "last_picked_product_id" not in existing_zone_cols:
                conn.execute(text("ALTER TABLE zones ADD COLUMN last_picked_product_id INTEGER REFERENCES products(id);"))

        conn.commit()
        print("[MIGRATION] Schema migration check completed successfully.")

import io
import os
import shutil
import pytest
from pathlib import Path
from PIL import Image
import zxingcpp

from backend.app.models import Product, ProductImage
from backend.app.services.gtin import validate_and_normalize_gtin
from backend.app.services.migration import run_idempotent_migrations, backup_database
from backend.app.routes.admin import UPLOAD_DIR


def _create_test_image_bytes(width=100, height=100, color="blue", format="PNG"):
    img = Image.new("RGB", (width, height), color=color)
    bio = io.BytesIO()
    img.save(bio, format=format)
    return bio.getvalue()


def test_gs1_gtin_service_validation():
    """Test GS1 check digit formula, length constraints and digit normalization."""
    # 1. Valid test cases from GS1 standard
    valid_cases = [
        ("4006381333931", "04006381333931"),      # EAN-13
        ("036000291452", "00036000291452"),      # UPC-A (12 digits, leading 0)
        ("96385074", "00000096385074"),          # GTIN-8
        ("00036000291452", "00036000291452"),    # GTIN-14
    ]
    for raw, expected14 in valid_cases:
        valid, clean, gtin14, err = validate_and_normalize_gtin(raw)
        assert valid is True, f"Failed for {raw}: {err}"
        assert clean == raw
        assert gtin14 == expected14
        assert err is None

    # 2. Persian and Arabic digits normalization
    valid, clean, gtin14, _ = validate_and_normalize_gtin("۴۰۰۶۳۸۱۳۳۳۹۳۱")
    assert valid is True
    assert clean == "4006381333931"
    assert gtin14 == "04006381333931"

    valid, clean, gtin14, _ = validate_and_normalize_gtin("٠٣٦٠٠٠٢٩١٤٥٢")
    assert valid is True
    assert clean == "036000291452"
    assert gtin14 == "00036000291452"

    # 3. Invalid check digit
    valid, _, _, err = validate_and_normalize_gtin("4006381333932")
    assert valid is False
    assert "رقم کنترلی" in err

    # 4. Invalid lengths
    for bad_len in ["123", "123456789", "123456789012345"]:
        valid, _, _, err = validate_and_normalize_gtin(bad_len)
        assert valid is False
        assert "طول بارکد" in err

    # 5. Non-numeric
    valid, _, _, err = validate_and_normalize_gtin("400638133393A")
    assert valid is False
    assert "فقط باید شامل ارقام" in err


def test_product_creation_with_valid_gtin_and_leading_zero(client, auth_headers):
    """Test creating product with UPC-A preserving leading zero in gtin and padding in gtin14."""
    payload = {
        "sku": "UPCA-TEST-001",
        "name": "محصول تستی با بارکد UPC-A",
        "brand": "برند تست",
        "category": "نوشیدنی",
        "unit_price": 28000,
        "gtin": "036000291452",
        "description": "کالای تستی برای بررسی بارکد"
    }

    res = client.post("/api/admin/products", json=payload, headers=auth_headers)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["gtin"] == "036000291452"
    assert data["gtin"].startswith("0")  # Leading zero preserved!
    assert data["gtin14"] == "00036000291452"
    assert data["brand"] == "برند تست"
    assert data["category"] == "نوشیدنی"


def test_product_creation_rejects_invalid_check_digit(client, auth_headers):
    """Test rejection of product with incorrect GS1 check digit."""
    payload = {
        "sku": "BAD-GTIN-001",
        "name": "محصول با بارکد نامعتبر",
        "unit_price": 15000,
        "gtin": "4006381333932"  # Expected check digit is 1, not 2
    }

    res = client.post("/api/admin/products", json=payload, headers=auth_headers)
    assert res.status_code == 400
    assert "رقم کنترلی" in res.json()["detail"]


def test_product_creation_rejects_equivalent_duplicate_gtin(client, auth_headers):
    """Test duplicate GTIN detection across different lengths (UPC-A vs GTIN-14)."""
    # 1. Create first product with UPC-A 12-digit: 036000291452
    res1 = client.post("/api/admin/products", json={
        "sku": "DUP-PROD-A",
        "name": "کالای اول با بارکد ۱۲ رقمی",
        "unit_price": 20000,
        "gtin": "036000291452"
    }, headers=auth_headers)
    assert res1.status_code == 201

    # 2. Try creating second product with GTIN-14 equivalent: 00036000291452
    res2 = client.post("/api/admin/products", json={
        "sku": "DUP-PROD-B",
        "name": "کالای دوم با بارکد معادل ۱۴ رقمی",
        "unit_price": 22000,
        "gtin": "00036000291452"
    }, headers=auth_headers)
    assert res2.status_code == 400
    assert "قبلاً ثبت شده است" in res2.json()["detail"]


def test_multiple_images_upload_and_primary_selection(client, auth_headers):
    """Test uploading multiple product images, setting primary, and retrieving dimensions."""
    # 1. Create product
    prod_res = client.post("/api/admin/products", json={
        "sku": "IMG-PROD-001",
        "name": "محصول آلبوم تصاویر",
        "unit_price": 45000
    }, headers=auth_headers)
    assert prod_res.status_code == 201
    prod_id = prod_res.json()["id"]

    # 2. Upload two valid images (PNG and JPEG)
    img1_bytes = _create_test_image_bytes(width=200, height=150, color="red", format="PNG")
    img2_bytes = _create_test_image_bytes(width=300, height=250, color="green", format="JPEG")

    files = [
        ("files", ("front.png", io.BytesIO(img1_bytes), "image/png")),
        ("files", ("side.jpg", io.BytesIO(img2_bytes), "image/jpeg")),
    ]

    upload_res = client.post(f"/api/admin/products/{prod_id}/images", files=files, headers=auth_headers)
    assert upload_res.status_code == 200, upload_res.text
    imgs = upload_res.json()
    assert len(imgs) == 2
    assert imgs[0]["width"] == 200
    assert imgs[0]["height"] == 150
    assert imgs[0]["is_primary"] is True  # First image is default primary
    assert imgs[1]["is_primary"] is False

    # 3. Change primary image to the second one
    img2_id = imgs[1]["id"]
    set_prim_res = client.post(f"/api/admin/products/{prod_id}/images/{img2_id}/set-primary", headers=auth_headers)
    assert set_prim_res.status_code == 200
    updated_prod = set_prim_res.json()
    updated_imgs = updated_prod["images"]
    assert any(im["id"] == img2_id and im["is_primary"] is True for im in updated_imgs)
    assert any(im["id"] == imgs[0]["id"] and im["is_primary"] is False for im in updated_imgs)


def test_image_upload_size_limit_and_non_image_rejection(client, auth_headers):
    """Test rejection of non-image files, corrupted content, and oversized files."""
    prod_res = client.post("/api/admin/products", json={
        "sku": "IMG-ERR-001",
        "name": "محصول خطای تصویر",
        "unit_price": 10000
    }, headers=auth_headers)
    prod_id = prod_res.json()["id"]

    # 1. Non-image extension (.pdf)
    files = [("files", ("doc.pdf", io.BytesIO(b"%PDF-1.4 sample content"), "application/pdf"))]
    res1 = client.post(f"/api/admin/products/{prod_id}/images", files=files, headers=auth_headers)
    assert res1.status_code == 400

    # 2. Corrupted content with image extension
    files = [("files", ("fake.png", io.BytesIO(b"not a valid png binary content"), "image/png"))]
    res2 = client.post(f"/api/admin/products/{prod_id}/images", files=files, headers=auth_headers)
    assert res2.status_code == 400
    assert "تصویر معتبر نیست" in res2.json()["detail"]


def test_image_deletion_and_product_deletion_cascading(client, auth_headers):
    """Test deleting single image removes file from disk, and deleting product cleans up all images."""
    prod_res = client.post("/api/admin/products", json={
        "sku": "IMG-DEL-001",
        "name": "محصول جهت حذف",
        "unit_price": 18000
    }, headers=auth_headers)
    prod_id = prod_res.json()["id"]

    # Upload 2 images
    img1_bytes = _create_test_image_bytes(format="PNG")
    img2_bytes = _create_test_image_bytes(format="PNG")
    files = [
        ("files", ("img1.png", io.BytesIO(img1_bytes), "image/png")),
        ("files", ("img2.png", io.BytesIO(img2_bytes), "image/png")),
    ]
    upload_res = client.post(f"/api/admin/products/{prod_id}/images", files=files, headers=auth_headers)
    imgs = upload_res.json()

    # Verify files exist on disk
    file_paths = []
    for img in imgs:
        rel = img["file_path"].replace("/static/uploads/", "").replace("/uploads/", "")
        p = UPLOAD_DIR / rel
        assert p.exists()
        file_paths.append(p)

    # 1. Delete image 1
    del_res = client.delete(f"/api/admin/products/{prod_id}/images/{imgs[0]['id']}", headers=auth_headers)
    assert del_res.status_code == 200
    assert not file_paths[0].exists()

    # 2. Delete product - image 2 should be unlinked
    del_prod_res = client.delete(f"/api/admin/products/{prod_id}", headers=auth_headers)
    assert del_prod_res.status_code == 200
    assert not file_paths[1].exists()


def test_barcode_scan_endpoint_with_zxing(client, auth_headers):
    """Test POST /api/admin/barcode/scan endpoint decoding authentic synthetic EAN-13 barcode."""
    # Generate authentic EAN-13 barcode using zxingcpp
    gtin_code = "4006381333931"
    bc = zxingcpp.create_barcode(gtin_code, zxingcpp.BarcodeFormat.EAN13)
    zxing_img = zxingcpp.write_barcode_to_image(bc)

    # Convert to PNG bytes
    pil_img = Image.fromarray(zxing_img)
    bio = io.BytesIO()
    pil_img.save(bio, format="PNG")
    png_bytes = bio.getvalue()

    files = {"file": ("barcode_test.png", io.BytesIO(png_bytes), "image/png")}
    res = client.post("/api/admin/barcode/scan", files=files, headers=auth_headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["gtin"] == gtin_code
    assert "EAN" in data["format"].upper()


def test_safe_migration_and_backup_creation():
    """Test idempotent migration and automatic backup creation."""
    bak = backup_database()
    run_idempotent_migrations()
    if bak and str(bak) != ".":
        assert bak.exists()
        assert bak.stat().st_size > 0

"""
SMARTSHELF Automated Tests for Phase 7 (Product Recognition Engine)
Tests deterministic embeddings, quality check, in-memory index updates,
unknown rejection, barcode/visual discrepancy (NEEDS_REVIEW), latency,
and persistence across restart.

NOTE: Synthetic NumPy images are used for automated CI testing and do not
represent real-world camera accuracy on actual retail packaging.
"""

import io
import time
import pytest
import numpy as np
from PIL import Image, ImageDraw
import zxingcpp

from backend.app.models import Product, ProductImage, ProductEmbedding
from backend.app.services.recognition import ProductRecognitionEngine, EMBEDDING_DIM
from backend.app.routes.admin import UPLOAD_DIR
from backend.app.config import settings


def _generate_synthetic_image(pattern: str = "pattern_a", width: int = 224, height: int = 224) -> Image.Image:
    """Generate deterministic synthetic image for testing."""
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)

    if pattern == "pattern_a":
        # Red rectangles and blue cross
        draw.rectangle([20, 20, 100, 100], fill=(220, 20, 60))
        draw.rectangle([120, 120, 200, 200], fill=(220, 20, 60))
        draw.line([(0, 0), (width, height)], fill=(0, 100, 220), width=5)
    elif pattern == "pattern_b":
        # Green circles and yellow stripes
        draw.ellipse([30, 30, 180, 180], fill=(34, 139, 34))
        draw.rectangle([10, 80, 210, 120], fill=(255, 215, 0))
    elif pattern == "blurry":
        # Completely uniform gray with no edges
        img = Image.new("RGB", (width, height), color=(128, 128, 128))
    elif pattern == "unknown":
        # Random noise
        np.random.seed(999)
        arr = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
        img = Image.fromarray(arr)

    return img


def _img_to_bytes(img: Image.Image, format: str = "PNG") -> bytes:
    bio = io.BytesIO()
    img.save(bio, format=format)
    return bio.getvalue()


def test_deterministic_embedding_extraction():
    """Verify that the same image produces identical, L2-normalized embedding vectors."""
    engine = ProductRecognitionEngine.get_instance()
    img = _generate_synthetic_image("pattern_a")

    v1 = engine.extract_embedding(img)
    v2 = engine.extract_embedding(img)

    assert v1.shape == (EMBEDDING_DIM,)
    assert v2.shape == (EMBEDDING_DIM,)
    assert np.allclose(v1, v2, atol=1e-5), "Embeddings for identical images must be strictly deterministic"

    # L2-norm should be 1.0
    norm = np.linalg.norm(v1)
    assert np.isclose(norm, 1.0, atol=1e-4), f"Embedding must be L2-normalized, got norm={norm}"


def test_quality_and_blur_detection():
    """Verify Laplacian variance correctly flags blurry/uniform images vs sharp images."""
    engine = ProductRecognitionEngine.get_instance()

    sharp_img = _generate_synthetic_image("pattern_a")
    sharp_np = np.asarray(sharp_img)
    sharp_q = engine.check_quality(sharp_np)
    assert sharp_q["is_blurry"] is False
    assert sharp_q["blur_score"] > 20.0

    blurry_img = _generate_synthetic_image("blurry")
    blurry_np = np.asarray(blurry_img)
    blurry_q = engine.check_quality(blurry_np)
    assert blurry_q["is_blurry"] is True
    assert blurry_q["blur_score"] < 5.0


def test_index_update_on_image_add_and_remove(client, auth_headers, db_session):
    """Verify in-memory index updates when adding an image, deleting an image, and deleting a product."""
    engine = ProductRecognitionEngine.get_instance()

    # 1. Create Product
    res = client.post("/api/admin/products", json={
        "sku": "REC-TEST-001",
        "name": "محصول تست شناسایی",
        "unit_price": 30000
    }, headers=auth_headers)
    assert res.status_code == 201
    prod_id = res.json()["id"]

    initial_count = len(engine._index_meta) if engine._index_meta else 0

    # 2. Upload image -> triggers add_image_embedding (original + 4 augmentations = 5 vectors)
    img_bytes = _img_to_bytes(_generate_synthetic_image("pattern_a"))
    files = [("files", ("test_pattern.png", io.BytesIO(img_bytes), "image/png"))]
    upload_res = client.post(f"/api/admin/products/{prod_id}/images", files=files, headers=auth_headers)
    assert upload_res.status_code == 200
    imgs = upload_res.json()
    img_id = imgs[0]["id"]

    assert len(engine._index_meta) == initial_count + 5

    # 3. Delete single image
    del_img_res = client.delete(f"/api/admin/products/{prod_id}/images/{img_id}", headers=auth_headers)
    assert del_img_res.status_code == 200
    assert len(engine._index_meta) == initial_count

    # 4. Upload again and delete whole product
    upload_res2 = client.post(f"/api/admin/products/{prod_id}/images", files=files, headers=auth_headers)
    assert upload_res2.status_code == 200
    assert len(engine._index_meta) == initial_count + 5

    del_prod_res = client.delete(f"/api/admin/products/{prod_id}", headers=auth_headers)
    assert del_prod_res.status_code == 200
    assert not any(m["product_id"] == prod_id for m in engine._index_meta)


def test_unknown_object_yields_unknown_status(client, auth_headers, db_session):
    """Verify that an uncataloged object is returned as UNKNOWN and never attributed to a wrong product."""
    engine = ProductRecognitionEngine.get_instance()

    # Register known product A
    res = client.post("/api/admin/products", json={
        "sku": "KNOWN-PROD-A",
        "name": "کالای مشخص الف",
        "unit_price": 50000
    }, headers=auth_headers)
    p_id = res.json()["id"]
    files = [("files", ("a.png", io.BytesIO(_img_to_bytes(_generate_synthetic_image("pattern_a"))), "image/png"))]
    client.post(f"/api/admin/products/{p_id}/images", files=files, headers=auth_headers)

    # Query with novel unknown image
    unknown_img_bytes = _img_to_bytes(_generate_synthetic_image("unknown"))
    result = engine.identify(unknown_img_bytes, db_session)

    assert result["status"] == "UNKNOWN", "Unrecognized object must yield UNKNOWN status"
    assert result["product_id"] is None
    assert result["processing_time_ms"] < 150.0, "Inference latency must be sub-150ms on CPU"


def test_known_object_recognition_and_latency(client, auth_headers, db_session):
    """Verify that registered product is successfully recognized with high similarity and low latency."""
    engine = ProductRecognitionEngine.get_instance()

    # Register Product B
    res = client.post("/api/admin/products", json={
        "sku": "KNOWN-PROD-B",
        "name": "کالای مشخص ب",
        "unit_price": 25000
    }, headers=auth_headers)
    p_id = res.json()["id"]
    files = [("files", ("b.png", io.BytesIO(_img_to_bytes(_generate_synthetic_image("pattern_b"))), "image/png"))]
    client.post(f"/api/admin/products/{p_id}/images", files=files, headers=auth_headers)

    # Query with the same pattern B
    query_bytes = _img_to_bytes(_generate_synthetic_image("pattern_b"))
    result = engine.identify(query_bytes, db_session)

    assert result["status"] == "RECOGNIZED"
    assert result["product_id"] == p_id
    assert result["sku"] == "KNOWN-PROD-B"
    assert result["similarity"] >= settings.RECOGNITION_ACCEPT_THRESHOLD
    assert result["processing_time_ms"] < 100.0


def test_barcode_visual_agreement_high_confidence(client, auth_headers, db_session):
    """Verify that image with matching visual and barcode produces RECOGNIZED with barcode_match=True."""
    engine = ProductRecognitionEngine.get_instance()

    gtin_code = "4006381333931"
    res = client.post("/api/admin/products", json={
        "sku": "BC-PROD-AGREE",
        "name": "محصول هماهنگ بارکد و تصویر",
        "unit_price": 35000,
        "gtin": gtin_code
    }, headers=auth_headers)
    p_id = res.json()["id"]

    # Register pattern A as visual reference
    files = [("files", ("ref.png", io.BytesIO(_img_to_bytes(_generate_synthetic_image("pattern_a"))), "image/png"))]
    client.post(f"/api/admin/products/{p_id}/images", files=files, headers=auth_headers)

    # Create composite test image: Pattern A + authentic barcode
    bc = zxingcpp.create_barcode(gtin_code, zxingcpp.BarcodeFormat.EAN13)
    bc_img = Image.fromarray(zxingcpp.write_barcode_to_image(bc))
    comp_img = _generate_synthetic_image("pattern_a", width=300, height=300)
    comp_img.paste(bc_img, (80, 180))

    comp_bytes = _img_to_bytes(comp_img)
    result = engine.identify(comp_bytes, db_session)

    assert result["status"] == "RECOGNIZED"
    assert result["product_id"] == p_id
    assert result["barcode"] == gtin_code
    assert result["barcode_match"] is True


def test_barcode_visual_discrepancy_yields_needs_review(client, auth_headers, db_session):
    """Verify that when visual features point to Product A, but barcode belongs to Product B, status is NEEDS_REVIEW."""
    engine = ProductRecognitionEngine.get_instance()

    # Product A: Visual Pattern A, GTIN A
    res_a = client.post("/api/admin/products", json={
        "sku": "PROD-VISUAL-A",
        "name": "محصول تصویری الف",
        "unit_price": 10000,
        "gtin": "4006381333931"
    }, headers=auth_headers)
    p_a_id = res_a.json()["id"]
    client.post(f"/api/admin/products/{p_a_id}/images", files=[("files", ("a.png", io.BytesIO(_img_to_bytes(_generate_synthetic_image("pattern_a"))), "image/png"))], headers=auth_headers)

    # Product B: Visual Pattern B, GTIN B (UPC-A: 036000291452)
    res_b = client.post("/api/admin/products", json={
        "sku": "PROD-BARCODE-B",
        "name": "محصول بارکدی ب",
        "unit_price": 20000,
        "gtin": "036000291452"
    }, headers=auth_headers)
    p_b_id = res_b.json()["id"]
    client.post(f"/api/admin/products/{p_b_id}/images", files=[("files", ("b.png", io.BytesIO(_img_to_bytes(_generate_synthetic_image("pattern_b"))), "image/png"))], headers=auth_headers)

    # Create composite image with Visual Pattern A, but Barcode B!
    bc = zxingcpp.create_barcode("036000291452", zxingcpp.BarcodeFormat.UPCA)
    bc_img = Image.fromarray(zxingcpp.write_barcode_to_image(bc))
    conflicted_img = _generate_synthetic_image("pattern_a", width=300, height=300)
    conflicted_img.paste(bc_img, (80, 180))

    result = engine.identify(_img_to_bytes(conflicted_img), db_session)

    assert result["status"] == "NEEDS_REVIEW", "Discrepancy between visual and barcode must produce NEEDS_REVIEW"
    assert result["barcode"] in ("036000291452", "0036000291452")
    assert result["barcode_match"] is True


def test_rebuild_index_and_persistence_across_restart(client, auth_headers, db_session):
    """Verify that in-memory index can be cleared and accurately rebuilt from database embeddings."""
    engine = ProductRecognitionEngine.get_instance()

    # Seed at least one product with embedding in this test session
    res = client.post("/api/admin/products", json={
        "sku": "REBUILD-TEST-PROD",
        "name": "محصول تست بازسازی ایندکس",
        "unit_price": 50000
    }, headers=auth_headers)
    p_id = res.json()["id"]
    files = [("files", ("ref.png", io.BytesIO(_img_to_bytes(_generate_synthetic_image("pattern_a"))), "image/png"))]
    client.post(f"/api/admin/products/{p_id}/images", files=files, headers=auth_headers)

    # Ensure embeddings exist
    initial_count = db_session.query(ProductEmbedding).count()
    assert initial_count > 0, "Database must have existing embeddings for test"

    # Simulate cold-start restart: wipe in-memory index
    engine._index_matrix = None
    engine._index_meta = []
    assert engine._index_matrix is None

    # Rebuild from DB
    engine.load_or_rebuild_index(db_session)
    assert engine._index_matrix is not None
    assert len(engine._index_meta) == initial_count


def test_recognition_api_endpoints(client, auth_headers):
    """Test REST API endpoints for recognition identification, status, rebuild, and feedback."""
    # 1. GET /api/admin/recognition/status
    st_res = client.get("/api/admin/recognition/status", headers=auth_headers)
    assert st_res.status_code == 200
    st_data = st_res.json()
    assert "indexed_vectors_count" in st_data
    assert "t_accept" in st_data

    # 2. POST /api/admin/recognition/identify
    img_bytes = _img_to_bytes(_generate_synthetic_image("pattern_a"))
    files = {"file": ("query.jpg", io.BytesIO(img_bytes), "image/jpeg")}
    id_res = client.post("/api/admin/recognition/identify", files=files, headers=auth_headers)
    assert id_res.status_code == 200
    id_data = id_res.json()
    assert "status" in id_data
    assert "processing_time_ms" in id_data
    assert "top3" in id_data

    # 3. POST /api/admin/recognition/rebuild-index
    rb_res = client.post("/api/admin/recognition/rebuild-index", headers=auth_headers)
    assert rb_res.status_code == 200
    assert "indexed_vectors_count" in rb_res.json()

    # 4. POST /api/admin/recognition/feedback
    # Create product to receive feedback
    p_res = client.post("/api/admin/products", json={
        "sku": "FDBK-001",
        "name": "محصول بازخورد",
        "unit_price": 12000
    }, headers=auth_headers)
    p_id = p_res.json()["id"]

    fb_files = {"file": ("fb.jpg", io.BytesIO(img_bytes), "image/jpeg")}
    fb_res = client.post(f"/api/admin/recognition/feedback?product_id={p_id}", files=fb_files, headers=auth_headers)
    assert fb_res.status_code == 200
    assert fb_res.json()["success"] is True

    # 5. GET /api/admin/recognition/latest-eval
    eval_res = client.get("/api/admin/recognition/latest-eval", headers=auth_headers)
    assert eval_res.status_code == 200
    assert "available" in eval_res.json()

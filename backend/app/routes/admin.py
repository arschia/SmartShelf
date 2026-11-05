import json
import os
import uuid
import shutil
import secrets
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, UploadFile, File
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from PIL import Image
import io
import numpy as np
import zxingcpp

from ..services.recognition import ProductRecognitionEngine
from ..models import Product, Zone, CustomerSession, EntryToken, Event, Device, Invoice, InvoiceLine, CartItem, ProductImage, ProductEmbedding, utc_now
from ..vision.camera_feed import camera_feed
from ..vision.occupancy import crop_relative_roi, extract_features
from ..vision.pipeline import pipeline
from ..ws import manager
from ..schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductImageResponse,
    ZoneResponse,
    ZoneAssignRequest,
    ZoneRoiUpdate,
    ZoneReferenceCaptureRequest,
    ZoneManualCorrectionRequest,
    EntryTokenResponse,
    SessionResponse,
    DeviceResponse,
    InvoiceResponse,
    InvoiceLineResponse,
)
from ..services.gtin import validate_and_normalize_gtin
from ..services.auth import (
    verify_admin_pin,
    create_admin_token,
    revoke_admin_token,
    get_current_admin,
    check_admin_lockout,
    record_failed_login,
    record_successful_login,
)
from ..services.event_service import get_cart_summary, record_system_event
from ..services.shop_scenario import demo_enabled, configuration as shop_configuration
from ..services.rate_limiter import login_limiter
from ..services.session_service import check_and_expire_idle_sessions
from ..services.camera_pairing import create_camera_pairing_code
from ..vision.camera_feed import camera_feed

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# Directory where uploaded images are saved
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
UPLOAD_DIR = Path(settings.UPLOAD_DIR).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Authentication Routes
# ---------------------------------------------------------------------------

@router.post("/login", response_model=AdminLoginResponse)
def admin_login(request: Request, payload: AdminLoginRequest, response: Response):
    """Authenticate admin with PIN and return auth token / set cookie."""
    check_admin_lockout(request)
    login_limiter.check(request)
    if not verify_admin_pin(payload.pin):
        record_failed_login(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect admin PIN",
        )

    record_successful_login(request)
    token = create_admin_token()

    # Set HTTP-only cookie for browser access
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        secure=settings.APP_ENV == "production" and settings.PUBLIC_BASE_URL.startswith("https://"),
        samesite="lax",
        max_age=settings.TOKEN_TTL_SECONDS,
    )

    return AdminLoginResponse(token=token, message="Authenticated successfully")


@router.post("/logout", dependencies=[Depends(get_current_admin)])
def admin_logout(response: Response, current_token: str = Depends(get_current_admin)):
    """Log out admin by revoking the token and clearing cookie."""
    revoke_admin_token(current_token)
    response.delete_cookie(key="admin_token")
    return {"message": "Logged out successfully"}


@router.get("/auth/check", dependencies=[Depends(get_current_admin)])
def admin_check_auth():
    """Verify that current admin session is valid."""
    return {"authenticated": True}


# ---------------------------------------------------------------------------
# Product CRUD & Image Routes (Protected)
# ---------------------------------------------------------------------------

def _build_product_response(p: Product) -> ProductResponse:
    images = []
    if hasattr(p, "images") and p.images:
        images = [
            ProductImageResponse(
                id=im.id,
                product_id=im.product_id,
                file_path=im.file_path,
                is_primary=im.is_primary,
                width=im.width,
                height=im.height,
                created_at=im.created_at,
            )
            for im in sorted(p.images, key=lambda x: (not x.is_primary, x.id))
        ]
    return ProductResponse(
        id=p.id,
        sku=p.sku,
        gtin=p.gtin,
        gtin14=p.gtin14,
        brand=p.brand,
        category=p.category,
        name=p.name,
        description=p.description,
        image_path=p.image_path,
        unit_price=p.unit_price,
        stock_quantity=p.stock_quantity,
        is_active=p.is_active,
        assigned_zones=[z.name for z in p.zones],
        images=images,
    )


@router.get("/products", response_model=List[ProductResponse], dependencies=[Depends(get_current_admin)])
def list_products(db: Session = Depends(get_db)):
    """List all products with assigned zones, GTIN, and images."""
    products = db.query(Product).order_by(Product.id.desc()).all()
    return [_build_product_response(p) for p in products]


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_current_admin)])
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    """Create a new product with validated price, unique SKU, and validated GS1 GTIN."""
    existing = db.query(Product).filter_by(sku=payload.sku.strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product with SKU '{payload.sku}' already exists",
        )

    gtin_clean = None
    gtin14_clean = None
    if payload.gtin and payload.gtin.strip():
        is_valid, gtin_clean, gtin14_clean, err = validate_and_normalize_gtin(payload.gtin)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

        dup_gtin = db.query(Product).filter_by(gtin14=gtin14_clean).first()
        if dup_gtin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"محصولی با این بارکد (یا معادل ۱۴ رقمی آن) قبلاً ثبت شده است (کد محصول: {dup_gtin.sku})"
            )

    product = Product(
        sku=payload.sku.strip(),
        gtin=gtin_clean,
        gtin14=gtin14_clean,
        brand=payload.brand.strip() if payload.brand else None,
        category=payload.category.strip() if payload.category else None,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        image_path=payload.image_path,
        unit_price=payload.unit_price,
        is_active=payload.is_active,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    if payload.image_path:
        pimg = ProductImage(
            product_id=product.id,
            file_path=payload.image_path,
            is_primary=True
        )
        db.add(pimg)
        db.commit()
        db.refresh(product)

    return _build_product_response(product)


@router.get("/products/{product_id}", response_model=ProductResponse, dependencies=[Depends(get_current_admin)])
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Retrieve details for a single product."""
    product = db.query(Product).filter_by(id=product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return _build_product_response(product)


@router.put("/products/{product_id}", response_model=ProductResponse, dependencies=[Depends(get_current_admin)])
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    """Update product details (name, price, active state, GTIN, brand, category)."""
    product = db.query(Product).filter_by(id=product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    next_active = product.is_active if payload.is_active is None else payload.is_active
    next_price = product.unit_price if payload.unit_price is None else payload.unit_price
    shop_cfg = shop_configuration(db)
    if shop_cfg and shop_cfg.product_id == product_id and db.query(CustomerSession).filter_by(status="ACTIVE").first() and (next_price != product.unit_price or not next_active):
        raise HTTPException(409, "در طول سشن خرید، قیمت یا فعال‌بودن محصول جایگاه قابل تغییر نیست.")
    if next_active and next_price <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="برای فعال‌سازی محصول، ابتدا قیمت فروش معتبر وارد کنید.")

    if payload.name is not None:
        product.name = payload.name.strip()
    if payload.brand is not None:
        product.brand = payload.brand.strip() if payload.brand else None
    if payload.category is not None:
        product.category = payload.category.strip() if payload.category else None
    if payload.description is not None:
        product.description = payload.description.strip() if payload.description else None
    if payload.image_path is not None:
        product.image_path = payload.image_path
    if payload.unit_price is not None:
        product.unit_price = payload.unit_price
    if payload.is_active is not None:
        product.is_active = payload.is_active

    if payload.gtin is not None:
        if payload.gtin.strip():
            is_valid, gtin_clean, gtin14_clean, err = validate_and_normalize_gtin(payload.gtin)
            if not is_valid:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

            dup = db.query(Product).filter(Product.gtin14 == gtin14_clean, Product.id != product_id).first()
            if dup:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"محصولی با این بارکد (یا معادل ۱۴ رقمی آن) قبلاً ثبت شده است (کد محصول: {dup.sku})"
                )
            product.gtin = gtin_clean
            product.gtin14 = gtin14_clean
        else:
            product.gtin = None
            product.gtin14 = None

    db.commit()
    db.refresh(product)
    return _build_product_response(product)


@router.delete("/products/{product_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(get_current_admin)])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Delete a product, unassign it from any linked shelf zones, and remove its images."""
    product = db.query(Product).filter_by(id=product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    shop_cfg = shop_configuration(db)
    if shop_cfg and shop_cfg.product_id == product_id and (shop_cfg.enabled or db.query(CustomerSession).filter_by(status="ACTIVE").first()):
        raise HTTPException(409, "پیش از حذف محصول، سناریو و سشن فعال را پایان دهید.")

    for zone in product.zones:
        zone.product_id = None
        zone.state = "EMPTY"

    for img in product.images:
        try:
            rel = img.file_path.replace("/static/uploads/", "").replace("/uploads/", "")
            fpath = UPLOAD_DIR / rel
            if fpath.exists():
                fpath.unlink()
        except Exception:
            pass

    db.delete(product)
    db.commit()

    ProductRecognitionEngine.get_instance().remove_product_from_index(product_id)

    return {"message": f"Product '{product.name}' deleted successfully"}


@router.post("/products/upload-image", dependencies=[Depends(get_current_admin)])
async def upload_product_image(file: UploadFile = File(...)):
    """Upload product image file with Pillow verification and save to uploads folder."""
    filename = file.filename or "image.png"
    ext = os.path.splitext(filename)[1].lower()
    allowed_exts = {".png", ".jpg", ".jpeg", ".webp"}
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: '{ext}'. فرمت‌های مجاز: {', '.join(allowed_exts)}"
        )

    contents = await file.read()
    try:
        pil_img = Image.open(io.BytesIO(contents))
        pil_img.verify()
        pil_img = Image.open(io.BytesIO(contents))
        img_format = (pil_img.format or ext.lstrip(".")).lower()
    except Exception:
        if contents.startswith(b"\x89PNG") or contents.startswith(b"\xff\xd8") or contents.startswith(b"RIFF"):
            img_format = ext.lstrip(".").lower()
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="محتوای فایل تصویر معتبر نیست")

    unique_name = f"{uuid.uuid4().hex[:16]}.{img_format}"
    dest_path = UPLOAD_DIR / unique_name

    with open(dest_path, "wb") as buffer:
        buffer.write(contents)

    return {"image_path": f"/static/uploads/{unique_name}"}


@router.post("/products/{product_id}/images", response_model=List[ProductImageResponse], dependencies=[Depends(get_current_admin)])
async def upload_multiple_product_images(product_id: int, files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Upload multiple product images (JPEG/PNG/WebP) with Pillow validation, dimensions, and path-traversal prevention."""
    product = db.query(Product).filter_by(id=product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    PRODUCTS_UPLOAD_DIR = UPLOAD_DIR / "products"
    PRODUCTS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    allowed_exts = {".png", ".jpg", ".jpeg", ".webp"}
    created_images = []

    for file in files:
        filename = file.filename or "image.jpg"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in allowed_exts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"فرمت فایل '{filename}' پشتیبانی نمی‌شود. فرمت‌های مجاز: JPEG, PNG, WebP"
            )

        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"حجم فایل '{filename}' بیشتر از حد مجاز (۵ مگابایت) است"
            )

        try:
            pil_img = Image.open(io.BytesIO(contents))
            pil_img.verify()
            pil_img = Image.open(io.BytesIO(contents))
            width, height = pil_img.size
            img_format = pil_img.format.lower()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"فایل '{filename}' تصویر معتبر نیست"
            )

        unique_name = f"{uuid.uuid4().hex}.{img_format}"
        dest_path = PRODUCTS_UPLOAD_DIR / unique_name

        with open(dest_path, "wb") as f:
            f.write(contents)

        file_url = f"/static/uploads/products/{unique_name}"
        has_primary = db.query(ProductImage).filter_by(product_id=product.id, is_primary=True).first() is not None
        is_primary = (not has_primary and len(created_images) == 0)

        pimg = ProductImage(
            product_id=product.id,
            file_path=file_url,
            is_primary=is_primary,
            width=width,
            height=height
        )
        db.add(pimg)
        db.flush()

        if is_primary:
            product.image_path = file_url

        created_images.append(pimg)

        # Extract deep feature embedding for product recognition (Phase 7)
        try:
            ProductRecognitionEngine.get_instance().add_image_embedding(
                db, product.id, pimg.id, pil_img, augment=True
            )
        except Exception as emb_err:
            print(f"[RECOGNITION] Warning: Could not generate embedding for image {pimg.id}: {emb_err}")

    db.commit()
    for im in created_images:
        db.refresh(im)

    return created_images


@router.delete("/products/{product_id}/images/{image_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(get_current_admin)])
def delete_product_image(product_id: int, image_id: int, db: Session = Depends(get_db)):
    """Delete a single product image, remove its embeddings, and unlink file from disk."""
    img = db.query(ProductImage).filter_by(id=image_id, product_id=product_id).first()
    if not img:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    was_primary = img.is_primary
    product = db.query(Product).filter_by(id=product_id).first()

    try:
        rel = img.file_path.replace("/static/uploads/", "").replace("/uploads/", "")
        fpath = UPLOAD_DIR / rel
        if fpath.exists():
            fpath.unlink()
    except Exception:
        pass

    db.delete(img)
    db.flush()

    if was_primary and product:
        next_img = db.query(ProductImage).filter_by(product_id=product_id).order_by(ProductImage.id.asc()).first()
        if next_img:
            next_img.is_primary = True
            product.image_path = next_img.file_path
        else:
            product.image_path = None

    db.commit()

    # Rebuild recognition index
    ProductRecognitionEngine.get_instance().remove_image_from_index(image_id, db)

    return {"message": "تصویر محصول با موفقیت حذف شد"}


@router.post("/products/{product_id}/images/{image_id}/set-primary", response_model=ProductResponse, dependencies=[Depends(get_current_admin)])
def set_primary_product_image(product_id: int, image_id: int, db: Session = Depends(get_db)):
    """Set an image as the primary display image of the product."""
    product = db.query(Product).filter_by(id=product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    target_img = db.query(ProductImage).filter_by(id=image_id, product_id=product_id).first()
    if not target_img:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    for im in product.images:
        im.is_primary = (im.id == image_id)

    product.image_path = target_img.file_path
    db.commit()
    db.refresh(product)
    return _build_product_response(product)


@router.post("/barcode/scan", dependencies=[Depends(get_current_admin)])
async def scan_barcode_from_image(file: UploadFile = File(...)):
    """Decode 1D/2D barcodes using local zxing-cpp library."""
    contents = await file.read()
    try:
        pil_img = Image.open(io.BytesIO(contents))
        pil_img.verify()
        pil_img = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="تصویر آپلود شده نامعتبر است")

    img_np = np.array(pil_img)
    barcodes = zxingcpp.read_barcodes(img_np)

    if not barcodes:
        return {"found": False, "message": "هیچ بارکدی در تصویر شناسایی نشد"}

    b = barcodes[0]
    raw_text = b.text
    is_valid_gtin, normalized_gtin, gtin14, err = validate_and_normalize_gtin(raw_text)

    return {
        "found": True,
        "gtin": normalized_gtin or raw_text,
        "text": raw_text,
        "format": str(b.format),
        "is_valid_gtin": is_valid_gtin,
        "normalized_gtin": normalized_gtin,
        "gtin14": gtin14,
        "error": err
    }


# ---------------------------------------------------------------------------
# Recognition Engine Endpoints (Phase 7)
# ---------------------------------------------------------------------------

@router.post("/recognition/identify", dependencies=[Depends(get_current_admin)])
async def identify_product_image(
    file: Optional[UploadFile] = File(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Identify product from uploaded image or webcam frame.
    Returns recognition status (RECOGNIZED/UNKNOWN/NEEDS_REVIEW), top-3 matches, and latency.
    """
    image_bytes = None
    if file:
        image_bytes = await file.read()
    elif request:
        try:
            body = await request.json()
            if "frame" in body and body["frame"]:
                frame_data = body["frame"]
                if "base64," in frame_data:
                    frame_data = frame_data.split("base64,")[1]
                import base64
                image_bytes = base64.b64decode(frame_data)
        except Exception:
            pass

    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فایل تصویر یا فریم وب‌کم ارسال نشده است"
        )

    engine = ProductRecognitionEngine.get_instance()
    result = engine.identify(image_bytes, db)
    return result


@router.get("/recognition/status", dependencies=[Depends(get_current_admin)])
def get_recognition_engine_status(db: Session = Depends(get_db)):
    """Return status, vector index count, and thresholds of the recognition engine."""
    engine = ProductRecognitionEngine.get_instance()
    idx_matrix = engine._index_matrix
    total_vectors = len(idx_matrix) if idx_matrix is not None else 0
    unique_products = len(set(m["product_id"] for m in engine._index_meta)) if engine._index_meta else 0

    return {
        "model_version": "mobilenetv2-7",
        "device": "CPU",
        "providers": engine.session.get_providers() if engine.session else [],
        "indexed_vectors_count": total_vectors,
        "unique_products_indexed": unique_products,
        "t_accept": settings.RECOGNITION_ACCEPT_THRESHOLD,
        "t_margin": settings.RECOGNITION_MARGIN_THRESHOLD,
    }


@router.post("/recognition/rebuild-index", dependencies=[Depends(get_current_admin)])
def rebuild_recognition_index(db: Session = Depends(get_db)):
    """Rebuild in-memory vector index from all database embeddings."""
    engine = ProductRecognitionEngine.get_instance()
    engine.load_or_rebuild_index(db)
    idx_matrix = engine._index_matrix
    count = len(idx_matrix) if idx_matrix is not None else 0
    return {"message": "شاخص برداری با موفقیت بازسازی شد", "indexed_vectors_count": count}


@router.post("/recognition/feedback", dependencies=[Depends(get_current_admin)])
async def submit_recognition_feedback(
    product_id: int,
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """
    Log recognition feedback and optionally attach image to the correct product to reinforce reference index.
    """
    prod = db.query(Product).filter_by(id=product_id).first()
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="محصول انتخاب‌شده یافت نشد")

    if file:
        contents = await file.read()
        try:
            pil_img = Image.open(io.BytesIO(contents)).convert("RGB")
            ProductRecognitionEngine.get_instance().add_image_embedding(
                db, prod.id, None, pil_img, augment=True
            )
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"خطا در پردازش تصویر: {e}")

    return {
        "success": True,
        "message": f"بازخورد ثبت شد و ویژگی‌های تصویر به محصول '{prod.name}' متصل گردید."
    }


@router.get("/recognition/latest-eval", dependencies=[Depends(get_current_admin)])
def get_latest_evaluation_report():
    """Retrieve the latest recognition evaluation report JSON."""
    latest_path = PROJECT_ROOT / "docs" / "eval" / "latest.json"
    if not latest_path.exists():
        return {"available": False, "message": "هنوز ارزیابی ثبت نشده است"}
    try:
        with open(latest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["available"] = True
            return data
    except Exception as e:
        return {"available": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Zone Management Routes (Protected)
# ---------------------------------------------------------------------------

@router.get("/zones", response_model=List[ZoneResponse], dependencies=[Depends(get_current_admin)])
def list_zones(db: Session = Depends(get_db)):
    """List all shelf zones with current product and state."""
    return db.query(Zone).order_by(Zone.id).all()


@router.put("/zones/{zone_id}/assign", response_model=ZoneResponse, dependencies=[Depends(get_current_admin)])
def assign_zone_product(zone_id: int, payload: ZoneAssignRequest, db: Session = Depends(get_db)):
    """Assign or unassign a product to a specific shelf slot."""
    zone = db.query(Zone).filter_by(id=zone_id).first()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    if payload.product_id is not None:
        product = db.query(Product).filter_by(id=payload.product_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        zone.product_id = product.id
        zone.state = "FULL"
    else:
        zone.product_id = None
        zone.state = "EMPTY"

    db.commit()
    db.refresh(zone)
    return zone


@router.post("/zones/{zone_id}/manual-correction", response_model=ZoneResponse, dependencies=[Depends(get_current_admin)])
def manual_zone_correction(zone_id: int, payload: ZoneManualCorrectionRequest, db: Session = Depends(get_db)):
    """
    Manually correct a zone's recognized product.
    If the zone has a recent in-memory ROI frame, it is saved as an additional reference image
    for the product and embedded into the recognition index.
    """
    zone = db.query(Zone).filter_by(id=zone_id).first()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    product = db.query(Product).filter_by(id=payload.product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # If there are in-memory ROI bytes for this zone, save as reference image and embed
    roi_bytes = pipeline.latest_zone_roi_bytes.get(zone.id)
    if roi_bytes:
        try:
            from PIL import Image
            import io
            pil_img = Image.open(io.BytesIO(roi_bytes)).convert("RGB")
            fname = f"corrected_z{zone.id}_{secrets.token_hex(6)}.png"
            dest = UPLOAD_DIR / fname
            pil_img.save(dest, format="PNG")
            img_rel = f"/static/uploads/products/{fname}"

            prod_img = ProductImage(
                product_id=product.id,
                file_path=img_rel,
                is_primary=False,
                width=pil_img.width,
                height=pil_img.height,
            )
            db.add(prod_img)
            db.flush()

            # Add to recognition engine
            engine = ProductRecognitionEngine.get_instance()
            engine.add_image_embedding(db, product.id, prod_img.id, pil_img, augment=True)
        except Exception as e:
            print(f"[RECOGNITION] Could not train embedding on manual correction: {e}")

    zone.recognized_product_id = product.id
    zone.recognition_status = "RECOGNIZED"
    zone.recognition_score = 1.0
    zone.last_recognized_at = utc_now()
    db.commit()
    db.refresh(zone)

    record_system_event(
        db=db,
        event_type="MANUAL_CORRECTION",
        zone_id=zone.id,
        product_id=product.id,
        status="PROCESSED",
    )
    return zone


# ---------------------------------------------------------------------------
# Entry QR Token & Customer Session Routes (Protected)
# ---------------------------------------------------------------------------

@router.post("/token", response_model=EntryTokenResponse, dependencies=[Depends(get_current_admin)])
@router.get("/token", response_model=EntryTokenResponse, dependencies=[Depends(get_current_admin)])
def generate_or_check_entry_token(db: Session = Depends(get_db)):
    """Generate a single-use entry QR token, or return occupied if a customer is inside."""
    if not settings.STORE_OPEN and not demo_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="فروشگاه بسته است / Store is closed"
        )
    check_and_expire_idle_sessions(db)
    now = utc_now()
    active_session = db.query(CustomerSession).filter(CustomerSession.status == "ACTIVE").first()
    if active_session:
        return EntryTokenResponse(
            active_session=True,
            token=None,
            expires_in=None,
            enter_url=None,
            message="فروشگاه در حال حاضر اشغال است / Store is occupied"
        )

    token_str = secrets.token_urlsafe(24)
    if demo_enabled(db):
        token_str = f"{secrets.randbelow(1_000_000):06d}"
        while db.query(EntryToken).filter_by(token=token_str).first():
            token_str = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = now + timedelta(seconds=settings.ENTRY_TOKEN_TTL_SECONDS)

    entry_token = EntryToken(
        token=token_str,
        created_at=now,
        expires_at=expires_at,
    )
    db.add(entry_token)
    db.commit()

    base_url = settings.FRONTEND_PUBLIC_URL.rstrip("/") if settings.FRONTEND_PUBLIC_URL else settings.PUBLIC_BASE_URL.rstrip("/")
    enter_url = f"{base_url}/enter?token={token_str}"
    if settings.FRONTEND_PUBLIC_URL and settings.PUBLIC_BASE_URL.startswith("https://"):
        from urllib.parse import quote
        enter_url += "&api=" + quote(settings.PUBLIC_BASE_URL, safe="")

    return EntryTokenResponse(
        active_session=False,
        token=token_str,
        expires_in=settings.ENTRY_TOKEN_TTL_SECONDS,
        enter_url=enter_url,
        message="کد ورود معتبر تولید شد / Valid entry code generated"
    )


@router.get("/sessions", response_model=List[SessionResponse], dependencies=[Depends(get_current_admin)])
def list_customer_sessions(db: Session = Depends(get_db)):
    """List all customer sessions with calculated duration."""
    now = utc_now()
    sessions = db.query(CustomerSession).order_by(CustomerSession.entered_at.desc()).all()
    results = []
    for s in sessions:
        if s.exited_at:
            duration = int((s.exited_at - s.entered_at).total_seconds())
        elif s.status == "ACTIVE":
            duration = int((now - s.entered_at).total_seconds())
        else:
            duration = 0

        inv = db.query(Invoice).filter_by(session_id=s.id).first()

        results.append(
            SessionResponse(
                id=s.id,
                status=s.status,
                entered_at=s.entered_at,
                exited_at=s.exited_at,
                exit_reason=s.exit_reason,
                duration_seconds=max(0, duration),
                invoice_id=inv.id if inv else None,
                invoice_total=inv.total if inv else None,
            )
        )
    return results


@router.post("/sessions/{session_id}/close", response_model=SessionResponse, dependencies=[Depends(get_current_admin)])
async def force_close_session(session_id: int, db: Session = Depends(get_db)):
    """Admin force-closes an active customer session."""
    session = db.query(CustomerSession).filter(CustomerSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.status == "ACTIVE":
        now = utc_now()
        session.status = "CLOSED"
        session.exited_at = now
        session.exit_reason = "ADMIN"

        event = Event(
            event_uid=secrets.token_hex(16),
            type="SESSION_CLOSED",
            session_id=session.id,
            confidence=1.0,
            status="PROCESSED",
            created_at=now
        )
        db.add(event)
        db.commit()
        db.refresh(session)

        # Notify via WebSocket
        await manager.broadcast_to_admins({
            "type": "SESSION_CLOSED",
            "session_id": session.id,
            "exited_at": session.exited_at.isoformat(),
            "exit_reason": "ADMIN"
        })
        await manager.broadcast_to_admins({
            "type": "EVENT_CREATED",
            "event": {
                "id": event.id,
                "event_uid": event.event_uid,
                "type": event.type,
                "session_id": event.session_id,
                "zone_id": None,
                "zone_name": None,
                "product_id": None,
                "product_name": None,
                "confidence": event.confidence,
                "status": event.status,
                "created_at": event.created_at.isoformat(),
            }
        })
        await manager.broadcast_to_customer(session.session_secret, {
            "type": "SESSION_CLOSED",
            "exit_reason": "ADMIN"
        })

    duration = int((session.exited_at - session.entered_at).total_seconds()) if session.exited_at else 0

    return SessionResponse(
        id=session.id,
        status=session.status,
        entered_at=session.entered_at,
        exited_at=session.exited_at,
        exit_reason=session.exit_reason,
        duration_seconds=max(0, duration)
    )


# ---------------------------------------------------------------------------
# Device & Camera Sensor Management Routes (Phase 4)
# ---------------------------------------------------------------------------

@router.get("/devices", response_model=List[DeviceResponse], dependencies=[Depends(get_current_admin)])
def list_devices(db: Session = Depends(get_db)):
    """List all registered devices and their online status."""
    return db.query(Device).order_by(Device.last_seen.desc()).all()


@router.get("/camera/status", dependencies=[Depends(get_current_admin)])
def get_camera_status():
    """Get real-time telemetry from in-memory camera feed."""
    return camera_feed.get_stats()


@router.post("/camera/pairing-code", dependencies=[Depends(get_current_admin)])
def generate_camera_pairing_code():
    """Admin creates a 6-digit camera pairing code valid for 5 minutes."""
    code = create_camera_pairing_code(validity_seconds=300)
    return {
        "code": code,
        "pairing_code": code,
        "expires_in": 300,
        "message": "کد جفت‌سازی ۵ دقیقه‌ای تولید شد"
    }


@router.get("/camera/latest-frame", dependencies=[Depends(get_current_admin)])
def get_camera_latest_frame(raw: bool = False):
    """Retrieve only a fresh camera frame JPEG from RAM; never serve a stale frame."""
    if not camera_feed.is_active(timeout_seconds=10.0):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if not raw:
        annotated = pipeline.get_annotated_jpeg()
        if annotated:
            return Response(content=annotated, media_type="image/jpeg")
    raw_frame = camera_feed.get_latest_jpeg()
    if raw_frame:
        return Response(content=raw_frame, media_type="image/jpeg")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Shelf Calibration & Reference Capture Routes (Phase 5)
# ---------------------------------------------------------------------------

@router.put("/zones/{zone_id}/roi", response_model=ZoneResponse, dependencies=[Depends(get_current_admin)])
def update_zone_roi(zone_id: int, payload: ZoneRoiUpdate, db: Session = Depends(get_db)):
    """Update relative ROI coordinates for a shelf slot."""
    zone = db.query(Zone).filter_by(id=zone_id).first()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    zone.roi_x = payload.roi_x
    zone.roi_y = payload.roi_y
    zone.roi_w = payload.roi_w
    zone.roi_h = payload.roi_h
    db.commit()
    db.refresh(zone)
    return zone


@router.post("/zones/{zone_id}/capture-reference", dependencies=[Depends(get_current_admin)])
def capture_zone_reference(zone_id: int, payload: ZoneReferenceCaptureRequest, db: Session = Depends(get_db)):
    """Capture computed reference features (HSV histogram + thumbnail) for a zone from latest RAM frame."""
    frame = camera_feed.get_latest_frame()
    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No camera feed available. Please connect tablet camera first."
        )

    zone = db.query(Zone).filter_by(id=zone_id).first()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    roi = crop_relative_roi(frame, zone.roi_x, zone.roi_y, zone.roi_w, zone.roi_h)
    if roi is None or roi.size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid zone ROI coordinates")

    features = extract_features(roi)
    ref_type = payload.reference_type.upper().strip()

    if ref_type == "FULL":
        zone.ref_full_features = json.dumps(features)
        zone.state = "PRESENT"
    elif ref_type == "EMPTY":
        zone.ref_empty_features = json.dumps(features)
        zone.state = "ABSENT"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reference_type must be FULL or EMPTY")

    db.commit()
    db.refresh(zone)

    return {
        "success": True,
        "zone_id": zone.id,
        "zone_name": zone.name,
        "reference_type": ref_type,
        "features_stored": {
            "hist_bins": len(features["hist"]),
            "thumb_pixels": len(features["thumb"]),
        },
        "message": f"Successfully captured {ref_type} reference for {zone.name}"
    }


@router.post("/zones/capture-all-full", dependencies=[Depends(get_current_admin)])
def capture_all_zones_full_reference(db: Session = Depends(get_db)):
    """Capture FULL reference features for all 3 zones at once from current RAM frame."""
    frame = camera_feed.get_latest_frame()
    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No camera feed available. Please connect tablet camera first."
        )

    zones = db.query(Zone).order_by(Zone.id).all()
    results = []
    for zone in zones:
        roi = crop_relative_roi(frame, zone.roi_x, zone.roi_y, zone.roi_w, zone.roi_h)
        if roi is not None and roi.size > 0:
            feats = extract_features(roi)
            zone.ref_full_features = json.dumps(feats)
            zone.state = "PRESENT"
            results.append(zone.name)

    db.commit()
    return {
        "success": True,
        "zones_calibrated": results,
        "message": f"Captured FULL reference for {len(results)} zones"
    }


# ---------------------------------------------------------------------------
# Events & Cart Telemetry Routes (Phase 6)
# ---------------------------------------------------------------------------

@router.get("/events", dependencies=[Depends(get_current_admin)])
def list_events(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    """List recorded system and vision events with zone/product details."""
    events = db.query(Event).order_by(Event.id.desc()).offset(offset).limit(limit).all()
    result = []
    for e in events:
        result.append({
            "id": e.id,
            "event_uid": e.event_uid,
            "type": e.type,
            "session_id": e.session_id,
            "device_id": e.device_id,
            "zone_id": e.zone_id,
            "zone_name": e.zone.name if e.zone else None,
            "product_id": e.product_id,
            "product_name": e.product.name if e.product else None,
            "confidence": e.confidence,
            "status": e.status,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })
    return result


@router.get("/sessions/{session_id}/cart", dependencies=[Depends(get_current_admin)])
def get_session_cart(session_id: int, db: Session = Depends(get_db)):
    """Retrieve current shopping cart for a given customer session."""
    session = db.query(CustomerSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return get_cart_summary(db, session_id)


# ---------------------------------------------------------------------------
# Invoices & Store Overview Routes (Phase 7)
# ---------------------------------------------------------------------------

@router.get("/invoices", response_model=List[InvoiceResponse], dependencies=[Depends(get_current_admin)])
def list_invoices(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """List customer invoices ordered by most recent."""
    return db.query(Invoice).order_by(Invoice.id.desc()).offset(offset).limit(limit).all()


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse, dependencies=[Depends(get_current_admin)])
def get_invoice_details(invoice_id: int, db: Session = Depends(get_db)):
    """Retrieve line items for a specific invoice."""
    inv = db.query(Invoice).filter_by(id=invoice_id).first()
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return inv


@router.get("/overview", dependencies=[Depends(get_current_admin)])
def get_store_overview(db: Session = Depends(get_db)):
    """Summary telemetry for Store Overview Dashboard."""
    check_and_expire_idle_sessions(db)
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Today's sessions count
    today_sessions = db.query(CustomerSession).filter(CustomerSession.entered_at >= today_start).count()

    # 2. Active session
    active_session = db.query(CustomerSession).filter_by(status="ACTIVE").order_by(CustomerSession.id.desc()).first()
    active_session_data = None
    if active_session:
        cart_info = get_cart_summary(db, active_session.id)
        active_session_data = {
            "id": active_session.id,
            "entered_at": active_session.entered_at.isoformat(),
            "items_count": cart_info["total_quantity"],
            "total_amount": cart_info["grand_total"],
        }

    # 3. Total invoices & revenue
    invoices = db.query(Invoice).all()
    total_invoices_count = len(invoices)
    total_revenue = sum(inv.total for inv in invoices)

    # 4. 3 Shelf slots status
    zones = db.query(Zone).order_by(Zone.id).all()
    zones_data = []
    for z in zones:
        p = z.product
        zones_data.append({
            "id": z.id,
            "name": z.name,
            "state": z.state or "PRESENT",
            "confidence": z.confidence,
            "product_name": p.name if p else "تخصیص نیافته",
            "unit_price": p.unit_price if p else 0,
        })

    # 5. Connected devices status and camera health watchdog
    camera_dev = db.query(Device).filter_by(role="CAMERA").order_by(Device.last_seen.desc()).first()
    camera_alive = camera_feed.is_active(timeout_seconds=10.0)
    camera_online = bool(camera_dev and camera_dev.is_online and camera_alive)
    camera_stale = bool(camera_dev and camera_dev.is_online and not camera_alive)

    devices_data = {
        "camera_online": camera_online,
        "camera_stale": camera_stale,
        "camera_device_id": camera_dev.device_id if camera_dev else None,
        "camera_last_seen": camera_dev.last_seen.isoformat() if (camera_dev and camera_dev.last_seen) else None,
        "total_devices": db.query(Device).count(),
    }

    return {
        "today_sessions_count": today_sessions,
        "active_session": active_session_data,
        "total_invoices_count": total_invoices_count,
        "total_revenue": total_revenue,
        "zones": zones_data,
        "devices": devices_data,
    }

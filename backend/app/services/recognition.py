"""
SMARTSHELF Product Recognition Engine (Phase 7)
Local ONNX-based product feature extraction, vector index, and barcode fusion.
Zero external/cloud API calls.
"""

import io
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import cv2
import numpy as np
import onnxruntime as ort
ort.disable_telemetry_events()
import zxingcpp
from PIL import Image, ImageEnhance
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Product, ProductImage, ProductEmbedding
from ..services.gtin import validate_and_normalize_gtin

# Model metadata
MODEL_VERSION = "mobilenetv2-7"
EMBEDDING_DIM = 1000

# ImageNet normalization parameters
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "frontend" / "static"
UPLOADS_DIR = Path(settings.UPLOAD_DIR).resolve()


class ProductRecognitionEngine:
    """
    Local CPU-based Product Recognition Engine using MobileNetV2 ONNX Runtime session,
    in-memory cosine similarity indexing, and zxing-cpp barcode fusion.
    """

    _instance: Optional["ProductRecognitionEngine"] = None

    def __init__(self):
        self.model_path = Path(settings.RECOGNITION_MODEL_PATH).resolve()
        if not self.model_path.exists():
            # Try relative to workspace root
            alt = Path(__file__).resolve().parent.parent.parent.parent / settings.RECOGNITION_MODEL_PATH
            if alt.exists():
                self.model_path = alt

        self.session: Optional[ort.InferenceSession] = None
        self._init_session()

        # In-memory index
        self._index_matrix: Optional[np.ndarray] = None  # Shape: (N, 1000), float32, L2-normalized
        self._index_meta: List[Dict[str, Any]] = []      # List of metadata dicts corresponding to rows

    @classmethod
    def get_instance(cls) -> "ProductRecognitionEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_session(self):
        """Initialize local ONNX Runtime inference session on CPU."""
        if not self.model_path.exists():
            print(f"[RECOGNITION WARNING] ONNX model not found at: {self.model_path}")
            return

        try:
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.session = ort.InferenceSession(
                str(self.model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"]
            )
            print(f"[RECOGNITION] Loaded ONNX model from {self.model_path} (providers: {self.session.get_providers()})")
        except Exception as e:
            print(f"[RECOGNITION ERROR] Failed to load ONNX model: {e}")
            self.session = None

    @staticmethod
    def check_quality(img_rgb: np.ndarray) -> Dict[str, Any]:
        """
        Assess image quality: blur detection using Laplacian variance.
        """
        try:
            gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
            variance = cv2.Laplacian(gray, cv2.CV_64F).var()
            is_blurry = bool(variance < 20.0)
            return {
                "blur_score": round(float(variance), 2),
                "is_blurry": is_blurry
            }
        except Exception:
            return {"blur_score": 0.0, "is_blurry": False}

    @staticmethod
    def preprocess_image(pil_img: Image.Image) -> np.ndarray:
        """
        Preprocess image for MobileNetV2:
        1. RGB conversion
        2. Center crop to square
        3. Resize to 224x224
        4. Normalize using ImageNet mean/std
        Returns array of shape (1, 3, 224, 224) float32.
        """
        img = pil_img.convert("RGB")
        w, h = img.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        img = img.crop((left, top, left + min_dim, top + min_dim))
        img = img.resize((224, 224), Image.Resampling.BILINEAR)

        arr = np.asarray(img, dtype=np.float32) / 255.0  # (224, 224, 3)
        arr = np.transpose(arr, (2, 0, 1))               # (3, 224, 224)
        arr = np.expand_dims(arr, axis=0)                # (1, 3, 224, 224)

        # Standardize
        norm = (arr - IMAGENET_MEAN) / IMAGENET_STD
        return norm.astype(np.float32)

    def extract_embedding(self, pil_img: Image.Image) -> np.ndarray:
        """
        Extract L2-normalized 1000-dimensional embedding vector from PIL image.
        """
        if self.session is None:
            # Fail closed: random vectors must never be mistaken for product identity.
            raise RuntimeError("Product identity model is unavailable; recognition is disabled")

        input_tensor = self.preprocess_image(pil_img)
        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: input_tensor})
        raw_vec = outputs[0][0].astype(np.float32)

        # L2-normalize
        norm = np.linalg.norm(raw_vec)
        if norm > 0:
            return raw_vec / norm
        return raw_vec

    def generate_augmentations(self, pil_img: Image.Image) -> List[Image.Image]:
        """
        Generate slight lighting/rotation variations during product registration (no horizontal flip).
        """
        augmented = [pil_img]

        # Brightness variations (+15% and -15%)
        enhancer = ImageEnhance.Brightness(pil_img)
        augmented.append(enhancer.enhance(1.15))
        augmented.append(enhancer.enhance(0.85))

        # Slight rotations (+4 and -4 degrees)
        augmented.append(pil_img.rotate(4, resample=Image.Resampling.BILINEAR, expand=False))
        augmented.append(pil_img.rotate(-4, resample=Image.Resampling.BILINEAR, expand=False))

        return augmented

    def load_or_rebuild_index(self, db: Session):
        """
        Build or rebuild the in-memory cosine similarity matrix from database embeddings.
        Automatically backfills embeddings for any catalog products with existing images.
        """
        embeddings = db.query(ProductEmbedding).all()

        # If database has images without embeddings, generate them automatically
        if not embeddings:
            self._backfill_existing_product_images(db)
            embeddings = db.query(ProductEmbedding).all()

        vectors = []
        meta = []

        for emb in embeddings:
            prod = db.query(Product).filter_by(id=emb.product_id).first()
            if not prod:
                continue

            v = np.frombuffer(emb.vector, dtype=np.float32)
            if v.shape[0] != EMBEDDING_DIM:
                continue

            # Ensure row is L2-normalized
            norm = np.linalg.norm(v)
            if norm > 0:
                v = v / norm

            vectors.append(v)
            meta.append({
                "embedding_id": emb.id,
                "image_id": emb.image_id,
                "product_id": prod.id,
                "sku": prod.sku,
                "name": prod.name,
                "brand": prod.brand,
                "category": prod.category,
                "gtin": prod.gtin,
                "gtin14": prod.gtin14,
                "image_path": prod.image_path or "/static/placeholder.png",
                "unit_price": prod.unit_price,
            })

        if vectors:
            self._index_matrix = np.vstack(vectors).astype(np.float32)
            self._index_meta = meta
        else:
            self._index_matrix = None
            self._index_meta = []

        print(f"[RECOGNITION] In-memory index built with {len(self._index_meta)} embeddings across {len(set(m['product_id'] for m in self._index_meta))} unique products.")

    def _backfill_existing_product_images(self, db: Session):
        """Backfill reference embeddings for seeded/existing products with image paths on disk."""
        products = db.query(Product).all()
        for prod in products:
            img_paths = []
            if prod.images:
                img_paths.extend([im.file_path for im in prod.images])
            elif prod.image_path:
                img_paths.append(prod.image_path)

            for ipath in img_paths:
                clean_path = str(ipath).replace("\\", "/").lstrip("/")
                if clean_path.startswith("static/"):
                    clean_path = clean_path[len("static/"):]
                # Do not resolve traversal or absolute paths from catalog records.
                relative_path = Path(clean_path)
                if ".." in relative_path.parts:
                    continue
                disk_file = STATIC_DIR / relative_path
                if clean_path.startswith("uploads/"):
                    disk_file = UPLOADS_DIR / clean_path[len("uploads/"):]
                if not disk_file.exists():
                    disk_file = UPLOADS_DIR / Path(ipath).name

                if disk_file.exists() and disk_file.is_file():
                    try:
                        with Image.open(disk_file) as img:
                            self.add_image_embedding(db, prod.id, None, img, augment=True)
                    except Exception as e:
                        print(f"[RECOGNITION] Could not backfill image {disk_file}: {e}")

    def add_image_embedding(
        self,
        db: Session,
        product_id: int,
        image_id: Optional[int],
        pil_img: Image.Image,
        augment: bool = True
    ) -> List[ProductEmbedding]:
        """
        Extract reference embedding (and variations) and save into database and in-memory index.
        """
        variants = self.generate_augmentations(pil_img) if augment else [pil_img]
        created = []

        new_vectors = []
        new_meta = []

        prod = db.query(Product).filter_by(id=product_id).first()
        prod_sku = prod.sku if prod else f"PROD-{product_id}"
        prod_name = prod.name if prod else ""
        prod_brand = prod.brand if prod else ""
        prod_cat = prod.category if prod else ""
        prod_gtin = prod.gtin if prod else ""
        prod_gtin14 = prod.gtin14 if prod else ""
        prod_img = prod.image_path if prod else "/static/placeholder.png"
        prod_price = prod.unit_price if prod else 0

        for var_img in variants:
            vec = self.extract_embedding(var_img)
            emb = ProductEmbedding(
                product_id=product_id,
                image_id=image_id,
                vector=vec.tobytes(),
                model_version=MODEL_VERSION,
            )
            db.add(emb)
            db.flush()
            created.append(emb)

            new_vectors.append(vec)
            new_meta.append({
                "embedding_id": emb.id,
                "image_id": image_id,
                "product_id": product_id,
                "sku": prod_sku,
                "name": prod_name,
                "brand": prod_brand,
                "category": prod_cat,
                "gtin": prod_gtin,
                "gtin14": prod_gtin14,
                "image_path": prod_img,
                "unit_price": prod_price,
            })

        db.commit()

        # Update in-memory index
        if self._index_matrix is None:
            self._index_matrix = np.vstack(new_vectors).astype(np.float32)
            self._index_meta = new_meta
        else:
            self._index_matrix = np.vstack([self._index_matrix, np.vstack(new_vectors)]).astype(np.float32)
            self._index_meta.extend(new_meta)

        return created

    def remove_product_from_index(self, product_id: int):
        """Remove a product from the in-memory index."""
        if self._index_matrix is None or not self._index_meta:
            return

        keep_indices = [i for i, m in enumerate(self._index_meta) if m["product_id"] != product_id]
        if not keep_indices:
            self._index_matrix = None
            self._index_meta = []
        else:
            self._index_matrix = self._index_matrix[keep_indices]
            self._index_meta = [self._index_meta[i] for i in keep_indices]

    def remove_image_from_index(self, image_id: int, db: Session = None):
        """Remove embeddings associated with an image from the in-memory index."""
        if self._index_matrix is None or not self._index_meta:
            return

        keep_indices = [i for i, m in enumerate(self._index_meta) if m.get("image_id") != image_id]
        if not keep_indices:
            self._index_matrix = None
            self._index_meta = []
        else:
            self._index_matrix = self._index_matrix[keep_indices]
            self._index_meta = [self._index_meta[i] for i in keep_indices]

    def search_top_k(self, query_vec: np.ndarray, k: int = 3) -> List[Dict[str, Any]]:
        """
        Compute cosine similarity of query vector against in-memory index.
        Groups multiple embeddings by product_id taking max similarity per product.
        """
        if self._index_matrix is None or len(self._index_meta) == 0:
            return []

        # Cosine similarity (vectors are L2-normalized)
        sims = np.dot(self._index_matrix, query_vec)

        # Max similarity per product
        product_best: Dict[int, Dict[str, Any]] = {}
        for idx, score in enumerate(sims):
            m = self._index_meta[idx]
            pid = m["product_id"]
            if pid not in product_best or score > product_best[pid]["similarity"]:
                product_best[pid] = {
                    "product_id": pid,
                    "sku": m["sku"],
                    "name": m["name"],
                    "brand": m.get("brand"),
                    "category": m.get("category"),
                    "gtin": m.get("gtin"),
                    "thumbnail": m.get("image_path"),
                    "unit_price": m.get("unit_price", 0),
                    "similarity": round(float(score), 4),
                }

        ranked = sorted(product_best.values(), key=lambda x: x["similarity"], reverse=True)
        return ranked[:k]

    def identify(self, image_bytes: bytes, db: Session) -> Dict[str, Any]:
        """
        Full Recognition Pipeline:
        1. Parse image and check Laplacian blur quality
        2. Detect 1D/2D barcode via local zxing-cpp
        3. Extract deep feature embedding and query in-memory index
        4. Apply decision rule with T_ACCEPT and T_MARGIN
        5. Fuse with barcode result (agreement, disagreement -> NEEDS_REVIEW, or visual-only)
        """
        t0 = time.perf_counter()

        # 1. Parse Image
        try:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img_np = np.asarray(pil_img)
        except Exception:
            return {
                "status": "UNKNOWN",
                "product_id": None,
                "sku": None,
                "name": None,
                "gtin": None,
                "similarity": 0.0,
                "margin": 0.0,
                "top3": [],
                "barcode": None,
                "barcode_match": False,
                "quality": {"blur_score": 0.0, "is_blurry": False},
                "processing_time_ms": round((time.perf_counter() - t0) * 1000, 2),
                "error": "فرمت تصویر معتبر نیست"
            }

        # Quality check
        quality = self.check_quality(img_np)

        # 2. Barcode Detection via zxing-cpp
        detected_barcode: Optional[str] = None
        barcode_product: Optional[Product] = None
        try:
            barcodes = zxingcpp.read_barcodes(img_np)
            if barcodes:
                raw_code = barcodes[0].text
                is_valid, clean_gtin, gtin14, _ = validate_and_normalize_gtin(raw_code)
                if is_valid:
                    detected_barcode = clean_gtin
                    barcode_product = db.query(Product).filter_by(gtin14=gtin14).first()
                else:
                    detected_barcode = raw_code
                    barcode_product = db.query(Product).filter((Product.gtin == raw_code) | (Product.sku == raw_code)).first()
        except Exception:
            detected_barcode = None
            barcode_product = None

        # 3. Extract Embedding & Cosine Search
        query_vec = self.extract_embedding(pil_img)
        top3 = self.search_top_k(query_vec, k=3)

        # 4. Decision Rule
        t_accept = settings.RECOGNITION_ACCEPT_THRESHOLD
        t_margin = settings.RECOGNITION_MARGIN_THRESHOLD

        visual_status = "UNKNOWN"
        top1_sim = top3[0]["similarity"] if top3 else 0.0
        top2_sim = top3[1]["similarity"] if len(top3) > 1 else 0.0
        margin = round(top1_sim - top2_sim, 4) if len(top3) > 1 else top1_sim

        if top3 and top1_sim >= t_accept:
            if len(top3) == 1 or margin >= t_margin:
                visual_status = "RECOGNIZED"
            else:
                visual_status = "UNKNOWN"  # Ambiguous close match

        # 5. Barcode Fusion
        final_status = visual_status
        matched_product_id: Optional[int] = None
        matched_sku: Optional[str] = None
        matched_name: Optional[str] = None
        matched_gtin: Optional[str] = None
        barcode_match: Optional[bool] = None

        if barcode_product:
            # Barcode was found and belongs to a registered product
            barcode_match = True
            if visual_status == "RECOGNIZED":
                if top3 and top3[0]["product_id"] == barcode_product.id:
                    # High confidence agreement!
                    final_status = "RECOGNIZED"
                    matched_product_id = barcode_product.id
                    matched_sku = barcode_product.sku
                    matched_name = barcode_product.name
                    matched_gtin = barcode_product.gtin
                else:
                    # Conflict between visual embedding and barcode!
                    final_status = "NEEDS_REVIEW"
                    matched_product_id = barcode_product.id
                    matched_sku = barcode_product.sku
                    matched_name = barcode_product.name
                    matched_gtin = barcode_product.gtin
            else:
                # Visual was UNKNOWN but barcode is 100% verified
                final_status = "RECOGNIZED"
                matched_product_id = barcode_product.id
                matched_sku = barcode_product.sku
                matched_name = barcode_product.name
                matched_gtin = barcode_product.gtin
        elif detected_barcode and not barcode_product:
            # Barcode read but not in catalog
            barcode_match = False
            if visual_status == "RECOGNIZED":
                final_status = "NEEDS_REVIEW"  # Mystery barcode on recognized object
            else:
                final_status = "UNKNOWN"
        else:
            # No barcode found in image -> rely on visual match
            barcode_match = None
            if visual_status == "RECOGNIZED" and top3:
                matched_product_id = top3[0]["product_id"]
                matched_sku = top3[0]["sku"]
                matched_name = top3[0]["name"]
                matched_gtin = top3[0].get("gtin")

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        return {
            "status": final_status,
            "product_id": matched_product_id,
            "sku": matched_sku,
            "name": matched_name,
            "gtin": matched_gtin,
            "similarity": top1_sim,
            "margin": margin,
            "top3": top3,
            "barcode": detected_barcode,
            "barcode_match": barcode_match,
            "thresholds": {
                "t_accept": t_accept,
                "t_margin": t_margin,
            },
            "quality": quality,
            "processing_time_ms": latency_ms
        }

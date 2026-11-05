
"""Two-reference shelf occupancy detector using local feature matching + RANSAC.

Reference images are converted to compact feature descriptors and stored in the
Zone reference columns. Raw reference/camera images are never written to disk.
"""
from __future__ import annotations

import base64
import json
import zlib
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

FEATURE_KIND = "two_reference_sift_ransac_v1"
MAX_FEATURES = 900
MIN_FEATURES = 8
MIN_INLIERS = 6
MIN_SCORE = 0.055
MIN_MARGIN = 0.12
LOWE_RATIO = 0.72
RANSAC_REPROJ_THRESHOLD = 4.0


class PresenceFeatureError(ValueError):
    """Raised when a reference or live frame cannot be used reliably."""


def _detector():
    # SIFT is more tolerant of scale/rotation than raw colour/pixel comparison.
    # ORB is retained as a compatibility fallback for OpenCV builds without SIFT.
    if hasattr(cv2, "SIFT_create"):
        return cv2.SIFT_create(nfeatures=MAX_FEATURES, contrastThreshold=0.025), cv2.NORM_L2, "SIFT", np.float32
    return cv2.ORB_create(nfeatures=MAX_FEATURES, scaleFactor=1.2, nlevels=8), cv2.NORM_HAMMING, "ORB", np.uint8


def crop_roi(image: np.ndarray, roi: Optional[list | tuple]) -> np.ndarray:
    if image is None or image.size == 0:
        raise PresenceFeatureError("تصویر خالی یا نامعتبر است")
    if roi is None:
        return image.copy()
    if len(roi) != 4:
        raise PresenceFeatureError("ROI باید شامل x، y، width و height باشد")
    x, y, w, h = [float(v) for v in roi]
    if not all(np.isfinite(v) for v in (x, y, w, h)):
        raise PresenceFeatureError("مختصات ROI معتبر نیست")
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1.0001 or y + h > 1.0001:
        raise PresenceFeatureError("ROI باید داخل تصویر و در بازه صفر تا یک باشد")
    ih, iw = image.shape[:2]
    x1, y1 = max(0, int(round(x * iw))), max(0, int(round(y * ih)))
    x2, y2 = min(iw, int(round((x + w) * iw))), min(ih, int(round((y + h) * ih)))
    if x2 - x1 < 24 or y2 - y1 < 24:
        raise PresenceFeatureError("محدوده انتخاب‌شده خیلی کوچک است")
    return image[y1:y2, x1:x2].copy()


def _extract(image: np.ndarray):
    if image is None or image.size == 0:
        raise PresenceFeatureError("تصویر قابل پردازش نیست")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    h, w = gray.shape[:2]
    if min(h, w) < 32:
        raise PresenceFeatureError("ابعاد تصویر برای تشخیص کافی نیست")
    detector, norm, algorithm, dtype = _detector()
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    if descriptors is None or len(keypoints) < MIN_FEATURES:
        raise PresenceFeatureError(
            f"جزئیات تصویری کافی نیست؛ حداقل {MIN_FEATURES} نقطه ویژگی لازم است"
        )
    if len(keypoints) > MAX_FEATURES:
        keypoints = keypoints[:MAX_FEATURES]
        descriptors = descriptors[:MAX_FEATURES]
    points = np.asarray([kp.pt for kp in keypoints], dtype=np.float32)
    descriptors = np.asarray(descriptors, dtype=dtype)
    return points, descriptors, norm, algorithm, (w, h)


def _pack_array(array: np.ndarray) -> str:
    raw = np.ascontiguousarray(array).tobytes()
    return base64.b64encode(zlib.compress(raw, level=6)).decode("ascii")


def _unpack_array(value: str, dtype: np.dtype, shape: tuple[int, ...]) -> np.ndarray:
    try:
        raw = zlib.decompress(base64.b64decode(value.encode("ascii"), validate=True))
        expected = int(np.prod(shape)) * np.dtype(dtype).itemsize
        if len(raw) != expected:
            raise ValueError("unexpected array length")
        return np.frombuffer(raw, dtype=dtype).reshape(shape).copy()
    except Exception as exc:
        raise PresenceFeatureError("داده مرجع خراب یا ناسازگار است") from exc


def build_reference(image: np.ndarray, roi: Optional[list | tuple] = None) -> dict:
    """Create a JSON-serializable feature reference from a full image and normalized ROI."""
    cropped = crop_roi(image, roi)
    points, descriptors, _, algorithm, size = _extract(cropped)
    desc_dtype = "float32" if algorithm == "SIFT" else "uint8"
    return {
        "kind": FEATURE_KIND,
        "algorithm": algorithm,
        "descriptor_dtype": desc_dtype,
        "width": int(size[0]),
        "height": int(size[1]),
        "count": int(len(points)),
        "points": _pack_array(points.astype("<f4")),
        "descriptors": _pack_array(descriptors.astype("<f4") if algorithm == "SIFT" else descriptors.astype("uint8")),
    }


def _decode_reference(reference: dict):
    if not isinstance(reference, dict) or reference.get("kind") != FEATURE_KIND:
        raise PresenceFeatureError("فرمت مرجع دو تصویری پشتیبانی نمی‌شود")
    count = int(reference.get("count", 0))
    if count < MIN_FEATURES or count > MAX_FEATURES:
        raise PresenceFeatureError("تعداد نقاط ویژگی مرجع معتبر نیست")
    algorithm = reference.get("algorithm")
    if algorithm == "SIFT" and reference.get("descriptor_dtype") == "float32":
        dtype, norm, width = np.float32, cv2.NORM_L2, 128
    elif algorithm == "ORB" and reference.get("descriptor_dtype") == "uint8":
        dtype, norm, width = np.uint8, cv2.NORM_HAMMING, 32
    else:
        raise PresenceFeatureError("نسخه الگوریتم مرجع شناخته‌شده نیست")
    points = _unpack_array(reference["points"], np.dtype("<f4"), (count, 2))
    desc_dtype = np.dtype("<f4") if algorithm == "SIFT" else np.dtype("uint8")
    descriptors = _unpack_array(reference["descriptors"], desc_dtype, (count, width))
    return points, descriptors, norm, algorithm, (int(reference["width"]), int(reference["height"]))


def _match(reference: dict, current: np.ndarray) -> dict:
    ref_points, ref_desc, norm, algorithm, ref_size = _decode_reference(reference)
    if current is None or current.size == 0:
        return {"score": 0.0, "inliers": 0, "matches": 0, "inlier_ratio": 0.0}
    # Keep the reference aspect ratio and scale range consistent when camera resolution changes.
    cur = cv2.resize(current, ref_size, interpolation=cv2.INTER_AREA) if current.shape[1::-1] != ref_size else current
    cur_points, cur_desc, _, cur_algorithm, _ = _extract(cur)
    if cur_algorithm != algorithm:
        return {"score": 0.0, "inliers": 0, "matches": 0, "inlier_ratio": 0.0}
    matcher = cv2.BFMatcher(norm)
    try:
        pairs = matcher.knnMatch(ref_desc, cur_desc, k=2)
    except cv2.error:
        return {"score": 0.0, "inliers": 0, "matches": 0, "inlier_ratio": 0.0}
    good = [m for pair in pairs if len(pair) == 2 for m, n in [pair] if m.distance < LOWE_RATIO * n.distance]
    if len(good) < 4:
        return {"score": 0.0, "inliers": 0, "matches": len(good), "inlier_ratio": 0.0}
    src = np.float32([ref_points[m.queryIdx] for m in good]).reshape(-1, 1, 2)
    dst = np.float32([cur_points[m.trainIdx] for m in good]).reshape(-1, 1, 2)
    try:
        _, mask = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_REPROJ_THRESHOLD)
    except cv2.error:
        mask = None
    if mask is None:
        return {"score": 0.0, "inliers": 0, "matches": len(good), "inlier_ratio": 0.0}
    inliers = int(mask.ravel().sum())
    ratio = inliers / max(1, len(good))
    denom = max(MIN_INLIERS, min(len(ref_points), len(cur_points)))
    score = min(1.0, (inliers / denom) * ratio)
    return {
        "score": round(float(score), 4),
        "inliers": inliers,
        "matches": len(good),
        "inlier_ratio": round(float(ratio), 4),
    }


def calibrate_pair(present_image: np.ndarray, empty_image: np.ndarray, roi: Optional[list | tuple] = None):
    """Validate two references and return compact features plus their visual separation."""
    present_crop = crop_roi(present_image, roi)
    empty_crop = crop_roi(empty_image, roi)
    if abs((present_crop.shape[1] / present_crop.shape[0]) - (empty_crop.shape[1] / empty_crop.shape[0])) > 0.04:
        raise PresenceFeatureError("نسبت ابعاد دو تصویر مرجع باید تقریباً یکسان باشد")
    # Normalize both crops to the same dimensions to avoid accidental aspect mismatch.
    if present_crop.shape[:2] != empty_crop.shape[:2]:
        empty_crop = cv2.resize(empty_crop, (present_crop.shape[1], present_crop.shape[0]), interpolation=cv2.INTER_AREA)
    full_ref = build_reference(present_crop)
    empty_ref = build_reference(empty_crop)
    # Estimate shared-scene overlap. Excessive overlap means the two references are
    # nearly identical; almost no overlap means the camera/scene changed too much.
    overlap = _match(full_ref, empty_crop)
    separation = round(max(0.0, min(1.0, 1.0 - overlap["score"])), 4)
    if separation < 0.07:
        raise PresenceFeatureError("دو مرجع تفاوت تصویری کافی ندارند؛ یک تصویر با محصول و دیگری بدون محصول بگیرید")
    if overlap["inliers"] < 4:
        # Very different backgrounds/camera positions are not a safe calibration pair.
        raise PresenceFeatureError("دو مرجع هم‌ترازی کافی ندارند؛ زاویه و محیط دوربین را ثابت کنید")
    return full_ref, empty_ref, {
        "separation": separation,
        "inliers": overlap["inliers"],
        "present_features": full_ref["count"],
        "empty_features": empty_ref["count"],
    }


def classify_frame(frame_roi: np.ndarray, full_ref: dict, empty_ref: dict):
    """Return PRESENT/ABSENT only when one reference clearly wins; otherwise UNKNOWN."""
    try:
        full = _match(full_ref, frame_roi)
        empty = _match(empty_ref, frame_roi)
    except PresenceFeatureError as exc:
        return "UNKNOWN", 0.0, {"reason": str(exc)}
    best_name, best, other = ("PRESENT", full, empty) if full["score"] > empty["score"] else ("ABSENT", empty, full)
    best_score = best["score"]
    margin = (best_score - other["score"]) / max(best_score, 1e-6)
    diagnostics = {
        "present_score": full["score"],
        "empty_score": empty["score"],
        "present_inliers": full["inliers"],
        "empty_inliers": empty["inliers"],
        "present_matches": full["matches"],
        "empty_matches": empty["matches"],
        "margin": round(float(margin), 4),
        "best_score": best_score,
    }
    if best["inliers"] < MIN_INLIERS or best_score < MIN_SCORE or margin < MIN_MARGIN:
        diagnostics["reason"] = "تطبیق دو مرجع به‌اندازه کافی متمایز نیست"
        return "UNKNOWN", 0.0, diagnostics
    confidence = min(0.99, max(0.5, 0.5 + (margin * min(1.0, best_score / 0.35)) * 0.49))
    return best_name, round(float(confidence), 3), diagnostics


def is_two_reference(reference: Optional[dict]) -> bool:
    return isinstance(reference, dict) and reference.get("kind") == FEATURE_KIND

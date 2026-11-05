"""Pure, testable vision module for slot occupancy detection.

Computes similarity scores using HSV Color Histograms + Normalized Grayscale thumbnail difference.
Outputs raw state: PRESENT, ABSENT, or UNKNOWN with confidence in [0.0, 1.0].
"""
from typing import Dict, Optional, Tuple, Any
import cv2
import numpy as np


def extract_features(roi: np.ndarray) -> Dict[str, Any]:
    """Extract computed feature representations from an image ROI.

    Returns:
        dict: {'hist': list of floats, 'thumb': list of ints}
    """
    if roi is None or roi.size == 0:
        return {"hist": [0.0] * 128, "thumb": [0] * 256}

    # 1. 2D HSV Histogram (Hue: 16 bins, Saturation: 8 bins = 128 bins)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    cv2.normalize(hist, hist, alpha=0.0, beta=1.0, norm_type=cv2.NORM_MINMAX)
    hist_list = hist.flatten().tolist()

    # 2. Downscaled Grayscale Thumbnail (16x16 = 256 pixels)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    thumb = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)
    thumb_list = [int(v) for v in thumb.flatten().tolist()]

    return {
        "hist": hist_list,
        "thumb": thumb_list,
    }


def compare_features(feat1: Dict[str, Any], feat2: Dict[str, Any], alpha: float = 0.5) -> float:
    """Compare two feature sets and return combined similarity score in [0.0, 1.0].

    Score 1.0 = identical, 0.0 = completely different.
    """
    if not feat1 or not feat2:
        return 0.0

    # 1. Histogram similarity via Bhattacharyya distance
    h1 = np.array(feat1.get("hist", []), dtype=np.float32).reshape(16, 8)
    h2 = np.array(feat2.get("hist", []), dtype=np.float32).reshape(16, 8)
    bhatt_dist = float(cv2.compareHist(h1, h2, cv2.HISTCMP_BHATTACHARYYA))
    # Bhattacharyya distance is in [0, 1], 0 is exact match
    sim_hist = max(0.0, min(1.0, 1.0 - bhatt_dist))

    # 2. Normalized Mean Absolute Difference of thumbnail pixels
    t1 = np.array(feat1.get("thumb", []), dtype=np.float32)
    t2 = np.array(feat2.get("thumb", []), dtype=np.float32)

    if len(t1) == len(t2) and len(t1) > 0:
        # Subtract mean to provide robust invariance against slight uniform lighting changes
        norm_t1 = t1 - np.mean(t1)
        norm_t2 = t2 - np.mean(t2)
        diff = np.mean(np.abs(norm_t1 - norm_t2)) / 128.0
        sim_pixel = max(0.0, min(1.0, 1.0 - diff))
    else:
        sim_pixel = 0.0

    # 3. Weighted combination
    combined = (alpha * sim_hist) + ((1.0 - alpha) * sim_pixel)
    return round(float(max(0.0, min(1.0, combined))), 3)


def classify_roi_occupancy(
    current_features: Dict[str, Any],
    ref_full: Optional[Dict[str, Any]] = None,
    ref_empty: Optional[Dict[str, Any]] = None,
    threshold_present: float = 0.60,
    threshold_absent: float = 0.60,
    alpha: float = 0.5,
) -> Tuple[str, float]:
    """Classify occupancy only when both references exist and clearly disagree.

    A missing reference or an ambiguous score must never be interpreted as the
    opposite state. This avoids the previous unsafe behavior where failure to
    match the only available reference was treated as proof of removal.
    """
    has_full = bool(ref_full and "hist" in ref_full and "thumb" in ref_full)
    has_empty = bool(ref_empty and "hist" in ref_empty and "thumb" in ref_empty)

    if not has_full or not has_empty:
        return "UNKNOWN", 0.0

    score_full = compare_features(current_features, ref_full, alpha)
    score_empty = compare_features(current_features, ref_empty, alpha)

    if score_full > score_empty:
        best_score = score_full
        threshold = threshold_present
        state = "PRESENT"
    elif score_empty > score_full:
        best_score = score_empty
        threshold = threshold_absent
        state = "ABSENT"
    else:
        return "UNKNOWN", 0.0

    margin = abs(score_full - score_empty)
    if best_score < threshold or margin < 0.08:
        return "UNKNOWN", round(float(best_score), 3)

    confidence = min(
        0.99,
        max(0.5, 0.5 + min(0.5, margin * 0.65 + max(0.0, best_score - threshold) * 0.35)),
    )
    return state, round(float(confidence), 3)


def crop_relative_roi(
    frame: np.ndarray,
    roi_x: float,
    roi_y: float,
    roi_w: float,
    roi_h: float,
) -> Optional[np.ndarray]:
    """Extract pixel ROI from a frame using resolution-independent relative coordinates in [0.0, 1.0]."""
    if frame is None or frame.size == 0:
        return None

    h, w = frame.shape[:2]

    # Convert normalized coords [0, 1] to pixel bounds
    x1 = max(0, min(w - 1, int(round(roi_x * w))))
    y1 = max(0, min(h - 1, int(round(roi_y * h))))
    x2 = max(x1 + 1, min(w, int(round((roi_x + roi_w) * w))))
    y2 = max(y1 + 1, min(h, int(round((roi_y + roi_h) * h))))

    if x2 <= x1 or y2 <= y1:
        return None

    return frame[y1:y2, x1:x2].copy()

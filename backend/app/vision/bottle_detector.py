"""Full-scene ONNX detector. Generic bottle detections never imply brand identity."""
from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
ort.disable_telemetry_events()

ROOT = Path(__file__).resolve().parents[3]
TARGET_CLASS = "heyjo_peach"
SUPPORTED_CLASSES = {"bottle", TARGET_CLASS, "other_bottle"}


def letterbox(frame, size=640):
    height, width = frame.shape[:2]
    scale = min(size / width, size / height)
    new_w, new_h = int(round(width * scale)), int(round(height * scale))
    left, top = (size - new_w) // 2, (size - new_h) // 2
    image = np.full((size, size, 3), 114, dtype=np.uint8)
    image[top:top + new_h, left:left + new_w] = cv2.resize(frame, (new_w, new_h))
    tensor = image[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    # Separate scale factors retain accuracy after rounding the resized dimensions.
    return np.ascontiguousarray(tensor), (new_w / width, new_h / height, left, top)


def decode_detections(output, names, transform, width, height, threshold=0.35):
    """Accept YOLO26 end-to-end (1,N,6) or raw YOLO11/26 (1,4+C,N)."""
    arr = np.asarray(output)
    if arr.ndim != 3 or arr.shape[0] != 1:
        raise ValueError("Unsupported detector output")
    raw = arr.shape[1] == 4 + len(names) and arr.shape[2] != 6
    if raw:
        candidates = arr[0].T
        class_ids = candidates[:, 4:].argmax(axis=1)
        scores = candidates[np.arange(len(candidates)), 4 + class_ids]
        xywh = candidates[:, :4]
        boxes = np.column_stack((xywh[:, 0] - xywh[:, 2] / 2,
                                 xywh[:, 1] - xywh[:, 3] / 2,
                                 xywh[:, 0] + xywh[:, 2] / 2,
                                 xywh[:, 1] + xywh[:, 3] / 2))
        candidates = np.column_stack((boxes, scores, class_ids))
    elif arr.shape[2] == 6:
        candidates = arr[0]
    else:
        raise ValueError("Unsupported detector output")
    sx, sy, left, top = transform
    found = []
    for row in candidates:
        if not np.isfinite(row).all() or row[4] < threshold or row[4] > 1:
            continue
        class_id = int(row[5])
        name = names.get(class_id, "")
        if name not in SUPPORTED_CLASSES:
            continue
        x1 = float(np.clip((row[0] - left) / sx / width, 0, 1))
        y1 = float(np.clip((row[1] - top) / sy / height, 0, 1))
        x2 = float(np.clip((row[2] - left) / sx / width, 0, 1))
        y2 = float(np.clip((row[3] - top) / sy / height, 0, 1))
        if x2 <= x1 or y2 <= y1:
            continue
        found.append({"box": [x1, y1, x2, y2], "confidence": round(float(row[4]), 4),
                      "class_name": name, "identity": TARGET_CLASS if name == TARGET_CLASS else "UNKNOWN",
                      "target": True if name == TARGET_CLASS else (False if name == "other_bottle" else None)})
    if raw:
        # Class-aware NMS: distinct objects/classes must not suppress each other.
        kept = []
        for name in SUPPORTED_CLASSES:
            items = [x for x in found if x["class_name"] == name]
            boxes = [[d["box"][0], d["box"][1], d["box"][2] - d["box"][0], d["box"][3] - d["box"][1]] for d in items]
            indices = cv2.dnn.NMSBoxes(boxes, [d["confidence"] for d in items], threshold, 0.45) if items else []
            kept.extend(items[int(i)] for i in np.asarray(indices).reshape(-1))
        found = kept
    return sorted(found, key=lambda d: d["confidence"], reverse=True)[:100]


class BottleDetector:
    def __init__(self, model_path=None):
        # A custom model is used only when explicitly configured. No startup download.
        from ..config import settings
        self.path = Path(model_path or settings.BOTTLE_MODEL_PATH)
        self.session = None
        self.names = {}
        self.error = None
        self.lock = threading.Lock()

    def load(self):
        if self.session is not None:
            return
        with self.lock:
            if self.session is not None:
                return
            if not self.path.is_file():
                self.error = "مدل تشخیص بطری نصب نشده است؛ بسته به‌روزرسانی را اجرا کنید."
                raise RuntimeError(self.error)
            try:
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2
                session = ort.InferenceSession(str(self.path), sess_options=opts, providers=["CPUExecutionProvider"])
                metadata = session.get_modelmeta().custom_metadata_map
                names = ast.literal_eval(metadata.get("names", "{}"))
                self.names = {int(k): str(v) for k, v in (names.items() if isinstance(names, dict) else enumerate(names))}
                inp = session.get_inputs()[0]
                if inp.shape != [1, 3, 640, 640] or not SUPPORTED_CLASSES.intersection(self.names.values()):
                    raise ValueError("Export a detection model with imgsz=640, batch=1, dynamic=False and supported class names")
                self.session = session
                self.error = None
            except Exception:
                self.error = "مدل قابل اجرا نیست؛ خروجی ONNX و نام کلاس‌ها را بررسی کنید."
                raise RuntimeError(self.error) from None

    def status(self):
        try:
            self.load()
        except RuntimeError:
            pass
        return {"ready": self.session is not None, "model": self.path.name,
                "mode": "custom_product" if TARGET_CLASS in self.names.values() else "generic_bottle",
                "classes": sorted(SUPPORTED_CLASSES.intersection(self.names.values())),
                "error": self.error, "brand_trained": TARGET_CLASS in self.names.values(),
                "transactions_enabled": False, "requires_empty_reference": False}

    def detect(self, frame, threshold=0.35):
        self.load()
        started = time.perf_counter()
        tensor, transform = letterbox(frame)
        with self.lock:
            output = self.session.run(None, {self.session.get_inputs()[0].name: tensor})[0]
        h, w = frame.shape[:2]
        detections = decode_detections(output, self.names, transform, w, h, threshold)
        return {"detections": detections, "bottle_count": len(detections),
                "target_count": sum(d["target"] is True for d in detections),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "image_size": [w, h], "model": self.path.name,
                "mode": "custom_product" if TARGET_CLASS in self.names.values() else "generic_bottle",
                "transactions_enabled": False}


_detector = None


def get_bottle_detector():
    global _detector
    if _detector is None:
        _detector = BottleDetector()
    return _detector

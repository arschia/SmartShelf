"""Explicitly reviewed training samples, private storage and environment-held-out export."""
from __future__ import annotations

import hashlib
import io
import json
import threading
import zipfile
from collections import Counter
from pathlib import Path

import cv2

CLASSES = {0: "heyjo_peach", 1: "other_bottle"}
_lock = threading.Lock()


def dataset_status(root):
    samples = read_samples(root)
    return {"samples": len(samples), "environments": sorted({s["environment"] for s in samples}),
            "class_instances": {name: sum(b["class_id"] == i for s in samples for b in s["boxes"]) for i, name in CLASSES.items()},
            "negative_images": sum(not s["boxes"] for s in samples),
            "export_ready": len({s["environment"] for s in samples}) >= 3}


def read_samples(root):
    path = Path(root)
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(path.glob("*.json"))] if path.exists() else []


def save_sample(root, frame, environment, boxes):
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    height, width = frame.shape[:2]
    if max(width, height) > 1600:
        factor = 1600 / max(width, height)
        frame = cv2.resize(frame, (round(width * factor), round(height * factor)))
    # Stable per-image key also prevents an identical frame leaking into two splits.
    sample_id = hashlib.sha256(frame.tobytes() + str(frame.shape).encode()).hexdigest()
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 94])
    if not ok:
        raise ValueError("Image encoding failed")
    record = {"id": sample_id, "environment": environment, "boxes": boxes,
              "reviewed": True, "image": sample_id + ".jpg", "size": list(frame.shape[1::-1])}
    with _lock:
        meta = path / (sample_id + ".json")
        if meta.exists():
            raise FileExistsError("این عکس قبلاً ثبت شده است؛ عکس متفاوتی بگیرید.")
        image_path = path / record["image"]
        image_path.write_bytes(encoded.tobytes())
        try:
            temporary = meta.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            temporary.replace(meta)
        except Exception:
            image_path.unlink(missing_ok=True)
            raise
    return record


def build_dataset_zip(root):
    """Never randomly split adjacent frames from the same room into train/test."""
    samples = read_samples(root)
    environments = sorted({s["environment"] for s in samples})
    if len(environments) < 3:
        raise ValueError("حداقل سه محیط مستقل ثبت کنید: یک محیط آزمون، یک محیط اعتبارسنجی و محیط‌های آموزش.")
    # Keep the two smallest groups entirely held out; users see the exact split map.
    counts = Counter(s["environment"] for s in samples)
    ordered = sorted(environments, key=lambda name: (counts[name], name))
    split_for = {name: "test" if i == 0 else "val" if i == 1 else "train" for i, name in enumerate(ordered)}
    report = {"classes": CLASSES, "environment_splits": split_for, "reviewed_samples": len(samples),
              "note": "Split by entire environment. These samples are not a validated model.",
              "sample_counts": dict(Counter(split_for[s["environment"]] for s in samples))}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.yaml", "train: images/train\nval: images/val\ntest: images/test\nnames:\n  0: heyjo_peach\n  1: other_bottle\n")
        archive.writestr("dataset_report.json", json.dumps(report, ensure_ascii=False, indent=2))
        for s in samples:
            split = split_for[s["environment"]]
            # Generated hex IDs only; metadata cannot redirect an export outside the dataset.
            sample_id = s["id"]
            if len(sample_id) != 64 or any(c not in "0123456789abcdef" for c in sample_id):
                raise ValueError("Invalid sample identifier")
            archive.write(Path(root) / (sample_id + ".jpg"), f"images/{split}/{sample_id}.jpg")
            lines = []
            for b in s["boxes"]:
                x1, y1, x2, y2 = b["box"]
                lines.append(f"{b['class_id']} {(x1+x2)/2:.7f} {(y1+y2)/2:.7f} {x2-x1:.7f} {y2-y1:.7f}")
            archive.writestr(f"labels/{split}/{sample_id}.txt", "\n".join(lines))
    return buffer.getvalue(), report

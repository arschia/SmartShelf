"""
SMARTSHELF Recognition Evaluation Script (Phase 7)
Evaluates recognition accuracy, per-class metrics, false recognition rate,
unknown detection rate, and latency (p50/p95).
Saves JSON and Markdown reports in docs/eval/.
"""

import os
import sys
import json
import time
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from backend.app.db import SessionLocal
from backend.app.models import Product
from backend.app.services.recognition import ProductRecognitionEngine, MODEL_VERSION
from backend.app.config import settings


def compute_dataset_hash(dataset_dir: Path) -> str:
    """Compute SHA-256 hash of all file names and bytes in the dataset directory."""
    hasher = hashlib.sha256()
    image_paths = sorted(list(dataset_dir.glob("*/*.*")))
    for p in image_paths:
        if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
            hasher.update(str(p.relative_to(dataset_dir)).encode("utf-8"))
            try:
                hasher.update(p.read_bytes())
            except Exception:
                pass
    return hasher.hexdigest()[:16]


def evaluate_dataset(dataset_dir: Path, output_dir: Path = None, db: Session = None) -> Dict[str, Any]:
    """Run full evaluation on dataset directory."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        engine = ProductRecognitionEngine.get_instance()
        engine.load_or_rebuild_index(db)

        dataset_hash = compute_dataset_hash(dataset_dir)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Map folders to ground-truth labels
        # Folders can be named after product SKU (e.g. MILK-001) or "unknown"
        subdirs = [d for d in dataset_dir.iterdir() if d.is_dir()]

        all_products = db.query(Product).all()
        sku_to_id = {p.sku: p.id for p in all_products}

        total_samples = 0
        correct_predictions = 0
        unknown_total = 0
        unknown_correct = 0
        known_total = 0
        false_recognition_count = 0  # Unknown recognized as known, or wrong known product assigned

        latencies = []
        per_class: Dict[str, Dict[str, int]] = {}

        # Confusion tracking: label -> list of results
        for sdir in subdirs:
            label = sdir.name  # "MILK-001" or "unknown"
            if label not in per_class:
                per_class[label] = {"tp": 0, "fp": 0, "fn": 0, "total": 0}

            image_files = [f for f in sdir.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]]
            for img_path in image_files:
                total_samples += 1
                per_class[label]["total"] += 1
                img_bytes = img_path.read_bytes()

                t0 = time.perf_counter()
                res = engine.identify(img_bytes, db)
                dt = (time.perf_counter() - t0) * 1000.0
                latencies.append(dt)

                pred_status = res["status"]
                pred_sku = res.get("sku")

                if label.lower() == "unknown":
                    unknown_total += 1
                    if pred_status == "UNKNOWN":
                        unknown_correct += 1
                        correct_predictions += 1
                        per_class[label]["tp"] += 1
                    else:
                        # False recognition! An unknown object was recognized as a known product
                        false_recognition_count += 1
                        per_class[label]["fn"] += 1
                else:
                    known_total += 1
                    if pred_status in ("RECOGNIZED", "NEEDS_REVIEW") and pred_sku == label:
                        correct_predictions += 1
                        per_class[label]["tp"] += 1
                    else:
                        per_class[label]["fn"] += 1
                        if pred_status == "RECOGNIZED" and pred_sku != label:
                            false_recognition_count += 1

        top1_accuracy = (correct_predictions / total_samples) if total_samples > 0 else 0.0
        udr = (unknown_correct / unknown_total) if unknown_total > 0 else 1.0
        frr = (false_recognition_count / total_samples) if total_samples > 0 else 0.0

        p50 = float(np.percentile(latencies, 50)) if latencies else 0.0
        p95 = float(np.percentile(latencies, 95)) if latencies else 0.0

        # Calculate per-class metrics
        class_metrics = {}
        for cls_name, counts in per_class.items():
            tp = counts["tp"]
            fn = counts["fn"]
            fp = counts["fp"]
            tot = counts["total"]
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
            class_metrics[cls_name] = {
                "total": tot,
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1": round(f1, 4),
            }

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_version": MODEL_VERSION,
            "dataset_hash": dataset_hash,
            "dataset_path": str(dataset_dir),
            "total_samples": total_samples,
            "known_samples": known_total,
            "unknown_samples": unknown_total,
            "top1_accuracy": round(top1_accuracy, 4),
            "false_recognition_rate": round(frr, 4),
            "unknown_detection_rate": round(udr, 4),
            "latency_ms": {
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "mean": round(float(np.mean(latencies)), 2) if latencies else 0.0,
            },
            "thresholds": {
                "t_accept": settings.RECOGNITION_ACCEPT_THRESHOLD,
                "t_margin": settings.RECOGNITION_MARGIN_THRESHOLD,
            },
            "per_class": class_metrics
        }

        # Write reports
        if output_dir is None:
            output_dir = PROJECT_ROOT / "docs" / "eval"
        output_dir.mkdir(parents=True, exist_ok=True)

        json_file = output_dir / f"evaluation_report_{timestamp}.json"
        md_file = output_dir / f"evaluation_report_{timestamp}.md"
        latest_json = output_dir / "latest.json"
        latest_md = output_dir / "latest.md"

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # Generate Markdown Report
        md_content = f"""# گزارش ارزیابی مدل شناسایی کالا (Product Recognition Report)

- **تاریخ ارزیابی:** {report['timestamp']}
- **نسخه مدل:** `{report['model_version']}`
- **هش مجموعه‌داده (Dataset SHA-256):** `{report['dataset_hash']}`
- **مسیر آزمون:** `{report['dataset_path']}`

---

## ۱. معیارهای کلیدی عملکرد

| شاخص | مقدار اندازه‌گیری‌شده | توضیحات |
| :--- | :--- | :--- |
| **دقت Top-1 (Accuracy)** | **{report['top1_accuracy'] * 100:.1f}%** | نسبت کل پیش‌بینی‌های صحیح به کل تصاویر |
| **نرخ تشخیص ناشناخته (UDR)** | **{report['unknown_detection_rate'] * 100:.1f}%** | درصد شناسایی صحیح اشیای خارج از کاتالوگ |
| **نرخ خطای شناسایی کاذب (FRR)** | **{report['false_recognition_rate'] * 100:.1f}%** | ورود اشتباه کالای متفرقه به سبد |
| **تأخیر پردازش p50** | **{report['latency_ms']['p50']} ms** | زمان پاسخ در ۵۰٪ موارد (CPU) |
| **تأخیر پردازش p95** | **{report['latency_ms']['p95']} ms** | زمان پاسخ در ۹۵٪ موارد (CPU) |

---

## ۲. آستانه‌های تصمیم‌گیری فعلی (.env)

- **آستانه پذیرش (`T_ACCEPT`):** `{report['thresholds']['t_accept']}`
- **حاشیه اطمینان نسبت به گزینه دوم (`T_MARGIN`):** `{report['thresholds']['t_margin']}`

---

## ۳. ارزیابی به تفکیک کلاس‌ها

| کلاس کالا (SKU) | تعداد نمونه | Precision | Recall | F1-Score |
| :--- | :---: | :---: | :---: | :---: |
"""
        for cls_name, m in report["per_class"].items():
            md_content += f"| `{cls_name}` | {m['total']} | {m['precision']:.3f} | {m['recall']:.3f} | **{m['f1']:.3f}** |\n"

        md_content += "\n---\n*این گزارش به صورت کامپایل محلی بر روی داده‌های آزمایشی واقعی استخراج شده است.*\n"

        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        # Save copy as latest
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        with open(latest_md, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"[EVALUATION] Completed. Top-1: {report['top1_accuracy']*100:.1f}%, UDR: {report['unknown_detection_rate']*100:.1f}%, FRR: {report['false_recognition_rate']*100:.1f}%, Latency p50: {report['latency_ms']['p50']}ms")
        print(f"[EVALUATION] Reports saved to {json_file} and {md_file}")

        return report

    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate SMARTSHELF product recognition engine.")
    parser.add_argument("--dataset", type=str, default="ai/evaluation/sample_dataset", help="Path to evaluation dataset")
    parser.add_argument("--output", type=str, default="docs/eval", help="Path to save evaluation reports")
    args = parser.parse_args()

    ds_path = Path(args.dataset).resolve()
    out_path = Path(args.output).resolve()
    if not ds_path.exists():
        print(f"Error: Dataset directory not found: {ds_path}")
        sys.exit(1)

    evaluate_dataset(ds_path, out_path)

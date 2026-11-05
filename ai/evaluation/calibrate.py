"""
SMARTSHELF Recognition Threshold Calibration Script (Phase 7)
Grid searches optimal T_ACCEPT and T_MARGIN thresholds on validation dataset
to minimize false recognition while maximizing recognition accuracy.
"""

import sys
import argparse
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image
import numpy as np
from backend.app.db import SessionLocal
from backend.app.models import Product
from backend.app.services.recognition import ProductRecognitionEngine


def calibrate_thresholds(dataset_dir: Path):
    """Run grid search over candidate T_ACCEPT and T_MARGIN."""
    db = SessionLocal()
    try:
        engine = ProductRecognitionEngine.get_instance()
        engine.load_or_rebuild_index(db)

        # Pre-extract embeddings for all validation images
        subdirs = [d for d in dataset_dir.iterdir() if d.is_dir()]
        samples = []

        print(f"[CALIBRATION] Loading validation images from {dataset_dir} ...")
        for sdir in subdirs:
            label = sdir.name
            is_unknown = (label.lower() == "unknown")
            files = [f for f in sdir.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]]
            for f in files:
                try:
                    with Image.open(f) as img:
                        vec = engine.extract_embedding(img)
                        top3 = engine.search_top_k(vec, k=3)
                        top1 = top3[0]["similarity"] if top3 else 0.0
                        top2 = top3[1]["similarity"] if len(top3) > 1 else 0.0
                        margin = top1 - top2 if len(top3) > 1 else top1
                        pred_sku = top3[0]["sku"] if top3 else None
                        samples.append({
                            "file": f.name,
                            "true_label": label,
                            "is_unknown": is_unknown,
                            "top1": top1,
                            "top2": top2,
                            "margin": margin,
                            "pred_sku": pred_sku,
                        })
                except Exception as e:
                    print(f"Skipping {f}: {e}")

        if not samples:
            print("[CALIBRATION] No valid images found for calibration.")
            return

        print(f"[CALIBRATION] Extracted embeddings for {len(samples)} test samples. Running grid search ...")

        accept_range = np.arange(0.50, 0.85, 0.05)
        margin_range = np.arange(0.04, 0.16, 0.02)

        best_score = -1.0
        best_t_accept = 0.65
        best_t_margin = 0.08
        best_stats = {}

        for t_acc in accept_range:
            for t_mar in margin_range:
                correct = 0
                false_rec = 0
                for s in samples:
                    is_recognized = (s["top1"] >= t_acc) and (s["margin"] >= t_mar)
                    if s["is_unknown"]:
                        if not is_recognized:
                            correct += 1
                        else:
                            false_rec += 1
                    else:
                        if is_recognized and s["pred_sku"] == s["true_label"]:
                            correct += 1
                        elif is_recognized and s["pred_sku"] != s["true_label"]:
                            false_rec += 1

                acc = correct / len(samples)
                frr = false_rec / len(samples)

                # Objective: Maximize accuracy while heavily penalizing False Recognition Rate (FRR)
                composite_score = acc - (3.0 * frr)
                if composite_score > best_score:
                    best_score = composite_score
                    best_t_accept = round(float(t_acc), 2)
                    best_t_margin = round(float(t_mar), 2)
                    best_stats = {
                        "accuracy": round(acc, 4),
                        "false_recognition_rate": round(frr, 4),
                        "composite_score": round(composite_score, 4)
                    }

        print("\n========================================================")
        print("  SMARTSHELF CALIBRATION RESULTS")
        print("========================================================")
        print(f"  Recommended RECOGNITION_ACCEPT_THRESHOLD : {best_t_accept}")
        print(f"  Recommended RECOGNITION_MARGIN_THRESHOLD : {best_t_margin}")
        print(f"  Expected Accuracy                        : {best_stats.get('accuracy', 0)*100:.1f}%")
        print(f"  Expected False Recognition Rate (FRR)    : {best_stats.get('false_recognition_rate', 0)*100:.2f}%")
        print("========================================================\n")
        print("To apply, update .env with:")
        print(f"RECOGNITION_ACCEPT_THRESHOLD={best_t_accept}")
        print(f"RECOGNITION_MARGIN_THRESHOLD={best_t_margin}")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate SMARTSHELF recognition thresholds.")
    parser.add_argument("--dataset", type=str, default="ai/evaluation/sample_dataset", help="Path to calibration dataset")
    args = parser.parse_args()

    ds_path = Path(args.dataset).resolve()
    if not ds_path.exists():
        print(f"Error: Dataset directory not found: {ds_path}")
        sys.exit(1)

    calibrate_thresholds(ds_path)

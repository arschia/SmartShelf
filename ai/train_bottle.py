"""Train reviewed, environment-separated data and export a CPU-ready custom detector.

Run on a training machine/Colab, not in the Windows serving environment.
The test set is evaluated once after selection of the best validation checkpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def audit_dataset(root):
    root = Path(root).resolve()
    report = json.loads((root / 'dataset_report.json').read_text(encoding='utf-8'))
    if set(report['environment_splits'].values()) != {'train','val','test'}:
        raise ValueError('Three independent environment splits are required.')
    hashes = set()
    counts = {}
    for split in ('train','val','test'):
        images = sorted((root / 'images' / split).glob('*.jpg'))
        classes, negative = Counter(), 0
        for image in images:
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            if digest in hashes:
                raise ValueError('Duplicate image detected across the dataset; remove duplicates before training.')
            hashes.add(digest)
            label = root / 'labels' / split / (image.stem + '.txt')
            lines = label.read_text().splitlines()
            negative += not lines
            for line in lines:
                parts = line.split()
                if len(parts) != 5 or parts[0] not in ('0','1'):
                    raise ValueError('Invalid YOLO annotation')
                import math
                coords = [float(v) for v in parts[1:]]
                if not all(math.isfinite(v) and 0 <= v <= 1 for v in coords) or min(coords[2:]) <= 0:
                    raise ValueError('Invalid YOLO coordinates')
                classes[int(parts[0])] += 1
        if not images or not classes[0] or not classes[1] or not negative:
            raise ValueError(f'{split}: include target bottles, OTHER bottles and empty/negative images in each environment split.')
        counts[split] = {'images':len(images),'heyjo_peach':classes[0],'other_bottle':classes[1],'negative_images':negative}
    return counts


def train(root, output, epochs=80, device='cpu'):
    root, output = Path(root).resolve(), Path(output).resolve()
    counts = audit_dataset(root)
    from ultralytics import YOLO
    # Absolute path is written only on the training machine, not baked into the dataset ZIP.
    config = root / 'data.runtime.yaml'
    config.write_text('path: ' + json.dumps(str(root)) + '\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: heyjo_peach\n  1: other_bottle\n')
    model = YOLO('yolo26n.pt')
    model.train(data=str(config), epochs=epochs, imgsz=640, device=device, batch=8,
                project=str(output), name='heyjo_peach', seed=42, deterministic=True,
                degrees=35, translate=.15, scale=.5, perspective=.0005,
                fliplr=0, flipud=0, hsv_h=.015, hsv_s=.5, hsv_v=.4,
                mosaic=1., close_mosaic=10, patience=20, workers=2)
    best = YOLO(str(Path(model.trainer.save_dir) / 'weights' / 'best.pt'))
    metrics = best.val(data=str(config), split='test', imgsz=640, device=device, plots=True)
    exported = best.export(format='onnx', imgsz=640, batch=1, dynamic=False, simplify=False, opset=17, nms=False, device='cpu')
    result = {'dataset_counts':counts,'test_metrics':metrics.results_dict,'onnx':str(exported),
              'classes':{0:'heyjo_peach',1:'other_bottle'},'evaluation':'Held-out environment test, not all-conditions guarantee',
              'activation':'Review per-class false positives and missed objects before configuring BOTTLE_MODEL_PATH.'}
    output.mkdir(parents=True,exist_ok=True)
    (output/'training_report.json').write_text(json.dumps(result,indent=2,default=float))
    print(json.dumps(result,indent=2,default=float))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',required=True,help='Extracted SmartShelf-bottle-dataset folder')
    parser.add_argument('--output',default='bottle-training-output')
    parser.add_argument('--epochs',type=int,default=80)
    parser.add_argument('--device',default='cpu',help='Use 0 for Colab GPU, cpu for CPU')
    parser.add_argument('--audit-only',action='store_true')
    args=parser.parse_args()
    if args.audit_only: print(json.dumps(audit_dataset(args.data),indent=2))
    else: train(args.data,args.output,args.epochs,args.device)

# Model card: generic bottle presence

## Intended use

CPU-local bottle detection for the one-location university scenario. The administrator assigns the catalog product to that location; the generic detector does not validate brand, flavor, price or an individual shopper's identity.

## Active model

| Field | Value |
| --- | --- |
| Model | Pretrained Ultralytics YOLO26n |
| Runtime file | `ai/models/yolo26n.onnx` |
| Source artifact | [Ultralytics assets v8.4.0](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.onnx) |
| SHA-256 | `2e947b787d9e787b93a16772a5f55b1d4d8c4d86f53146149c5d6a642442d6f7` |
| Bytes | 9,941,957 |
| Execution | ONNX Runtime, local CPU |
| Preprocessing | 640-pixel letterbox, RGB, NCHW float32, divide by 255 |
| Output handling | End-to-end `(1,N,6)` or supported raw class output; normalized coordinates; class-aware NMS for raw output |
| Default lab confidence threshold | 0.35 |
| Recognized supported classes | Generic `bottle`, or explicitly configured custom `heyjo_peach` / `other_bottle` outputs |
| Generic identity result | `UNKNOWN`; no brand identity is inferred from a generic bottle box |

The bundled artifact checksum matches the upstream release metadata. The application filters supported classes, validates finite coordinates/scores and clamps boxes. The scenario uses detections relative to a configured physical ROI, followed by its temporal state machine.

## Training status

No successfully trained, independently validated brand-specific model is asserted for this release. Reference capture, catalog embeddings and reviewed annotation counts are not neural-network fine-tuning.

The repository provides `ai/train_bottle.py`, a notebook, training requirements and annotation/export tools. Export splits by whole environment so a classroom is not casually shared across train/validation/test groups. A future model should report independent labels, sample counts, held-out environments, thresholds, errors and deployment runtime before replacing the generic model.

## Available checks

- `docs/BOTTLE_BASELINE_EVALUATION.json` records 42 supplied-image checks; 39 images produced one or more bottle detections and 3 produced none. One documented empty sample had no bottle detection. The other non-detections and extra background boxes are relevant failure cases.
- This is not a fully annotated held-out dataset. No mAP, precision, recall or generalization percentage is reported from those counts.
- `docs/LIVE_SHOP_MODEL_SMOKE.json` records an isolated real-model → HTTP frames → SQLite → customer-WebSocket smoke test. Baseline, removal, repeated absence and return produced the expected cart/stock sequence.
- Owner acceptance on 5 Nov 2026 confirms the owner's demonstration worked; it is not an independent multi-environment evaluation.
- Original private reference photographs are not included in this public repository.

## Limitations and failure modes

Occlusion, motion blur, small/distant objects, severe lighting, top-down views, reflections and background bottles can affect detections. A confidence score is not a probability that charging a customer is correct. A missing box in one frame is not proof of a removal. The temporal/ROI/session rules reduce unsafe transitions but do not establish production accuracy.

The current accounting scenario cannot count several bottles in a slot or determine which of multiple shoppers removed an item. Do not extend its capacity merely by adding detection boxes to a UI.

## Legacy identity model

`ai/models/mobilenetv2-7.onnx` is retained for the earlier catalog/embedding path. Its SHA-256 is `c1c513582d56afceff8516c73804e484c81c6a830712ab6d682253f4a3cd042f` (14,246,826 bytes). It is not a bottle-brand classifier trained by this project. The Windows installer deliberately selects a disabled/unvalidated identity path by default. Historical identity-evaluation notes should not be read as the performance of the active generic bottle detector.

## Provenance and notices

Model files are versioned with [checksums](../ai/models/checksums.json). The YOLO model is distributed with its upstream AGPL-3.0 notice. See [third-party notices](../THIRD_PARTY_NOTICES.md) for upstream source and retained licenses. Third-party licensing is not replaced by this model card.

# Third-party provenance and licensing

This repository preserves third-party notices and does not claim ownership of upstream models, fonts or libraries. No blanket relicense of every project/third-party asset is asserted by this publication. Project-owned source has not been assigned an additional general-purpose reuse license in this import; contact the maintainer for permissions beyond the terms that otherwise apply.

| Component | Provenance | Retained notice / status |
| --- | --- | --- |
| YOLO26n ONNX | [Ultralytics assets v8.4.0](https://github.com/ultralytics/assets/releases/tag/v8.4.0), [upstream source](https://github.com/ultralytics/ultralytics) | `ai/models/YOLO-AGPL-3.0-LICENSE.txt`; upstream model/code licensing remains applicable |
| MobileNetV2-7 ONNX | [ONNX Model Zoo](https://github.com/onnx/models/tree/main/validated/vision/classification/mobilenet) | Apache-2.0 upstream repository notice; legacy identity path, not a custom trained product model |
| jsQR 1.4.0 | [cozmo/jsQR](https://github.com/cozmo/jsQR) | `frontend/assets/js/jsQR-LICENSE.txt` |
| Vazirmatn v33.003 | [rastikerdar/vazirmatn](https://github.com/rastikerdar/vazirmatn) | `frontend/assets/fonts/OFL.txt`, SIL Open Font License 1.1 |
| Python dependencies | Exact versions in `requirements.txt` and related requirement files | Their individual upstream licenses apply; installing dependencies does not transfer their copyright to SmartShelf |

The original deployment used Dana font files. The supplied file labeled as a font license did not contain redistribution terms, so those binaries are not published here. The public source uses locally bundled Vazirmatn instead. CSS retains the `Dana` family name as a compatibility alias for that replacement. Screenshots depict the owner's existing deployed UI; they are not bundled font software.

Project interface images and diagrams accompany the documentation. User-private reference-photo archives, runtime uploads and personal configuration are excluded. The generic detector's reviewed-image summary is metadata, not a license to the original private photographs.

See `ai/models/checksums.json` and `docs/MODEL_CARD.md` for artifact identity and the limits of reported model checks.

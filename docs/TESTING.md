# Validation and reproducibility

## Evidence levels

| Evidence | What it supports | What it does not establish |
| --- | --- | --- |
| Backend pytest: 160 passed, 0 failed/errors | Tested service, API, security, persistence and vision-state regressions in the recorded isolated environment | Universal device/network accuracy or production readiness |
| Eight executable Node UI harnesses | Actual shipped handlers/modules exercised at browser/network boundaries | A physical browser video benchmark |
| Real bundled-ONNX smoke test | Present → empty → empty → present produced stock/cart 1/0 → 0/1 → 0/1 → 1/0 in an isolated DB | Generalized recognition across all classrooms |
| 42 supplied reference-image checks | 39 images produced at least one bottle detection; results recorded in JSON | mAP, precision/recall or a held-out benchmark without full ground-truth annotation |
| Owner acceptance, 5 Nov 2026 | Owner reported the tablet/store setup working after 1.4.1 | Independently measured FPS, field reliability or multi-customer support |

The reference-image JSON is an image-presence check, not a training log. Original private reference photos are not included in the public repository.

## Run backend tests

```bash
python -m pytest backend/tests -q
```

Tests select a test-only configuration and an in-memory SQLite DB. Do not run them against a store's production database. The recorded QA run used a Linux x86-64 kernel network-denial wrapper to prevent outbound native-library telemetry:

```bash
python scripts/qa_no_network.py backend/tests -q
```

That wrapper is platform-specific and denies Internet socket creation; it is not a portable Windows test runner. ONNX Runtime telemetry is also disabled in the application. No unapproved outbound telemetry is required to validate the project.

## Run browser-side logic tests

```bash
node scripts/test_pairing_ui.cjs
node scripts/test_camera_startup.cjs
node scripts/test_camera_transport_ui.cjs
node scripts/test_rtc_ui.cjs
node scripts/test_shop_ui.cjs
node scripts/test_shop_tablet_controls.cjs
node scripts/test_bottle_ui.cjs
node scripts/test_entry_qr.cjs
```

These use controlled DOM, media, network and peer-connection boundaries while executing actual project JavaScript. They cover localized pairing codes, permission-versus-playback errors, WSS/HTTPS fallback, frame backpressure, offer/answer/ICE, control acknowledgments, stale responses, independent video/inference controls, and live stock/cart updates.

## Static release checks

```bash
python scripts/release_selfcheck.py
python scripts/check_frontend_paths.py
```

`scripts/predeploy_check.py` additionally requires a real, private deployment `.env`; it is expected to fail on a clean public checkout until configuration is supplied. CI source checks should not invent production secrets to claim deployment approval.

## Physical acceptance checklist

1. Pair a tablet and verify increasing confirmed frame count at the backend.
2. Confirm actual WebRTC receive FPS; then pause inference and verify video remains visible.
3. Start inference from the manager; require tablet acknowledgment plus new frames from the same device.
4. Configure one bottle and ROI, establish baseline, and open one customer session.
5. Remove/return the bottle; verify both browsers update without manual refresh.
6. Test brief ambiguity, a blocked lens, a network interruption and a session switch; none should charge an unrelated customer.
7. Restart the backend and verify persistent data plus conservative temporal-state recovery.

Keep failure cases and raw test results when measuring performance. A successful demonstration is not a statistical evaluation.

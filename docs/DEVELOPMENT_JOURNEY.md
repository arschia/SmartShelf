# From reference matching to a portable live-store demo

This is a reconstruction of the actual development milestones, not fabricated Git history. The initial GitHub import contains the already-developed project; the notes below explain why the design evolved.

## 1. Start with a concrete cashierless scenario

The goal was to demonstrate a customer entering with a code/QR, removing a bottle, seeing a live cart update, returning the bottle and seeing both stock and cart recover. A tablet replaces a dedicated camera. A browser serves both manager and customer. The project is intended to be carried between classrooms.

## 2. Build a fixed-shelf, two-reference baseline

The initial vision approach compared a configured ROI against present and empty references. OpenCV SIFT/ORB features, geometric matching with RANSAC and a temporal state machine made the baseline more conservative than a raw pixel difference. It passed an initial owner-run demonstration with two references, but moving the camera or changing the background exposed the limits of reference matching.

That implementation remains available in the recognition/calibration tooling. It is useful to study, but it is not the detector required by the current portable bottle scenario.

## 3. Separate product identity from object presence

Legacy MobileNetV2 embedding/catalog work did not establish reliable recognition of a specific bottle brand. Adding reference pictures is not fine-tuning a neural network. The owner accepted generic bottle recognition for the university demonstration, so the design moved to pretrained YOLO26n exported to ONNX and executed locally with ONNX Runtime.

An administrator maps the single physical location to the named product. The detector answers whether a bottle intersects that location. Training scripts, an annotation/export workflow and a notebook provide a future custom-model route; a successfully trained brand-specific model is **not** claimed.

## 4. Choose a deployable local backend

Railway packaging and persistent-volume checks were prepared first. The connected account could not deploy under its trial restriction, and the owner selected the second architecture: Windows hosting the backend, SQLite and inference, Tailscale Funnel for HTTPS/WSS, and Vercel for the existing frontend. The local computer must remain powered, online and awake.

## 5. Wire the accounting loop

Version 1.3.0 introduced the single-bottle scenario: establish inventory from stable presence, charge only an eligible active customer on a stable removal, and reverse the owning cart on return. Server broadcasts keep manager and customer screens live. QR/manual entry uses the same session model; no client-side mock cart events are accepted as purchases.

## 6. Make transport failures visible

Version 1.3.1 added signed camera credentials, explicit WSS authentication deadlines, frame acknowledgments/backpressure and an authenticated HTTPS frame-upload fallback. Entry scanning was added with the vendored jsQR library and localized numeral normalization.

Version 1.3.2 fixed a real camera-startup regression: a removed WebRTC callback was still invoked after `getUserMedia()` succeeded. The resulting JavaScript exception had been incorrectly reported as a camera-permission failure. Error messages now distinguish permission, busy hardware, playback, constraints and page-code failures.

## 7. Replace snapshot viewing with WebRTC

Version 1.4.0 replaced the manager's 1.5-second JPEG polling and the shop's one-shot preview with native WebRTC video. Authenticated HTTPS signaling, ICE negotiation, receiver-measured FPS and track replacement were implemented without introducing a public unauthenticated signaling relay. Inference frames remained separate from high-FPS preview video.

Version 1.4.1 corrected the tablet Start button. It had only opened video and displayed a message. It now sends an acknowledged command over a reliable data channel and verifies new frames from that device at the backend. Stop pauses inference-frame transmission while preview video can continue.

## 8. Verify, then document the accepted result

The backend suite recorded 160 passing tests. Browser-side logic was exercised through executable Node harnesses for pairing, camera startup, transport failover, RTC negotiation/control and live-shop updates. An isolated real-ONNX integration smoke test recorded baseline → removal → repeated absence → return with the expected SQLite/cart/WebSocket results.

On 5 November 2026 the owner reported that the physical setup was working correctly and requested this GitHub publication. That report is field acceptance, not a benchmark across arbitrary cameras, classrooms or networks. Automated browser-harness results are not represented as physical-device FPS measurements.

## Next research questions

- Measure missed detections, occlusions and false removals using independently labeled classroom scenes.
- Study multiple bottles/locations and customer attribution before increasing store capacity.
- Evaluate a brand-specific model with environment-disjoint train/validation/test sets.
- Add a verified TURN deployment if cross-network demonstrations need it.
- Establish backup/restore and operational monitoring beyond the university setup.

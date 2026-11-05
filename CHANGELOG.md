# 1.4.1 — Tablet Start/Stop fix

Reliable WebRTC data-channel commands with tablet acknowledgment; server frame growth bound to the same tablet before success; explicit pending/error states; no duplicate inference stream; WebRTC preview survives AI pause. Web-only update compatible with backend 1.4.0.

# 1.4.0 — WebRTC tablet video

Authenticated HTTPS signaling; direct video-only 720p/30 FPS target in admin and live shop. Receiver-measured FPS, bounded transient queues, camera track replacement, viewer cleanup and explicit TURN configuration. Vision/accounting frame transport stays independent.

## 2026-11-03 — Deployment-ready patch

- Added Dockerfile, Railway config, persistent `/data` volume instructions and one-worker startup.
- Restored `.env.example`, `.gitignore` and complete README that were omitted from prior release ZIP.
- Fixed backend routing for uploaded images on a persistent volume and cross-origin frontend media URLs.
- Fixed QR TTL to 30 seconds (separate from admin token TTL), and carried public backend origin in first-time entry QR.
- Disabled cart mutations in `STORE_OPEN=false` calibration mode.
- Fail-closed when ONNX model unavailable; no pseudo-embeddings.
- Prevented event UID reuse after process restart.
- Added read-only backend verification and Windows bootstrap scripts.
- No production deploy and no live tablet validation yet.

# Changelog — SmartShelf

## 2026-11-03 — Two-reference integration and public-release hardening

### Added
- Integrated two-reference calibration UI into the admin recognition tab.
- Added authenticated `/api/presence` API for calibration, manual detection and clearing a zone reference.
- Added SIFT + RANSAC feature matching with ORB fallback.
- Persisted per-zone reference descriptors in the existing Zone database fields.
- Connected the new detector to the live vision pipeline while preserving legacy HSV references.

### Fixed
- Missing or mixed references now result in `UNKNOWN`, never an inferred removal.
- Ambiguous two-reference matches return `UNKNOWN`.
- Unknown observations reset the continuous debounce window.
- Fixed debounce behavior when the monotonic test clock starts at zero.
- Camera frame input size, dimensions and device ID are validated.
- Stale camera frames are no longer served as live frames.
- Camera device token moved from WebSocket URL query string to the first authenticated WSS message.
- Camera UI waits for an authenticated connection acknowledgement before showing Online.
- Admin and customer pages no longer fall back to simulated login, cart or invoice data when the backend is unavailable.
- Removed public ntfy and PeerJS relay paths from operational frontend code.
- Removed legacy client-side sample-product pick/return event generator.
- Unified admin token and cookie lifetime through `TOKEN_TTL_SECONDS`.
- Production startup rejects weak/default admin PINs and weak placeholder secret keys.

### Release safety
- Default `STORE_OPEN` in `.env.example` is now `false`.
- Public release check requires a strong PIN, secret key, correct CORS origin, and matching HTTPS backend URL in `PUBLIC_BASE_URL` and `frontend/config.js`.
- Release archive excludes `.env`, SQLite databases/backups, certificates/private keys, Git history, cache files and user-uploaded files.

### Validation
- Python compileall passed.
- Main JavaScript syntax checks passed.
- Two-reference detector tests: 4 passed.
- Occupancy/state-machine tests: 6 passed.
- Security token/PIN tests: 2 passed.
- Camera input-limit test: 1 passed.
- Direct SQLite API calibration/detect/clear cycle passed.
- Full test suite not run in the current environment because `onnxruntime` and `zxingcpp` are not installed.
- Real tablet/camera validation remains required.

# Configuration reference

| Setting | Purpose | Guidance |
| --- | --- | --- |
| `APP_ENV` | Security mode | Use production for the real host. |
| `SECRET_KEY` | HMAC signing key | Generate locally; strong random value, at least 32 characters. |
| `ADMIN_PIN` | Manager sign-in | Strong local credential; never publish it. |
| `ALLOW_INSECURE_TEST_PIN` | Explicit closed-store test-only exception | Not needed for normal installation; never use it to open a real store. |
| `STORE_OPEN` | Normal store admission | Defaults false. The separately enabled university scenario has explicit demo admission rules. |
| `DB_URL` | SQLAlchemy database URL | Local SQLite normally in `data/smartshelf.db`. |
| `UPLOAD_DIR` | Explicit uploaded assets | Normally `data/uploads`; outside Git. |
| `PUBLIC_BASE_URL` | HTTPS backend origin | Your Funnel hostname, without a trailing slash. |
| `FRONTEND_PUBLIC_URL` | Web frontend origin | Your Vercel/custom frontend origin. |
| `ALLOWED_ORIGINS` | CORS allowlist | Exact local/frontend origins; do not use a blanket origin for authenticated browser access. |
| `TRUST_PROXY` | Forwarded-client-IP handling | False unless the deployment has a deliberately trusted proxy boundary. |
| `TOKEN_TTL_SECONDS` | Admin credential lifetime | Default 28800; validated range 60–86400. |
| `ENTRY_TOKEN_TTL_SECONDS` | One-use customer entry lifetime | Default 30; validated range 15–300. |
| `SESSION_IDLE_TIMEOUT` | Abandoned session expiry | Default 900 seconds. |
| `BOTTLE_MODEL_PATH` | Generic or explicitly supplied custom ONNX | Default `ai/models/yolo26n.onnx`. |
| `BOTTLE_DATASET_DIR` | Reviewed annotation data | Default `data/bottle_dataset`; never publish private datasets by accident. |
| `RECOGNITION_MODEL_PATH` | Legacy catalog identity model | The Windows installer disables unvalidated identity inference by selecting a non-installed identity path. |
| `RTC_ICE_SERVERS` | Optional STUN/TURN configuration | JSON array supplied only to authenticated peers. |

Example ICE configuration, using placeholders rather than working credentials:

```dotenv
RTC_ICE_SERVERS=[{"urls":"stun:stun.l.google.com:19302"},{"urls":"turns:YOUR-TURN-HOST:443?transport=tcp","username":"YOUR-USERNAME","credential":"YOUR-CREDENTIAL"}]
```

Frontend `window.SMARTSHELF_CONFIG.apiBase` contains a public origin only. The browser server-settings control can select a different origin for your own installation. Never put an admin PIN, device token, private key or TURN secret in that file.

Changing backend `.env` settings requires a backend restart. Restarting or reloading a viewer reconnects WebRTC; SDP/ICE sessions are not persisted.

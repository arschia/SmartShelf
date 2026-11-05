# API and event guide

Use the running backend's `/docs` or `/openapi.json` as the exact route/schema reference. This document explains the principal interfaces; it does not replace the generated API definition.

| Interface | Authentication / role | Purpose |
| --- | --- | --- |
| `POST /api/admin/login` | Admin PIN | Issue signed admin credential. |
| `GET /api/admin/auth/check` | Admin bearer token/cookie | Validate manager session. |
| `POST /api/admin/token` | Admin | Generate short-lived, one-use customer entry token. |
| `/api/entry/*` | Entry/session-specific | Customer admission, cart and checkout flow. |
| `/api/admin/products`, `/api/admin/zones` | Admin | Catalog, stock/location configuration and references. |
| `GET /api/admin/camera/status` | Admin | Confirm live frames, device ID, frame counter and inference transport FPS. |
| `POST /api/camera/pair` | One-use device pairing code | Exchange code for signed device-bound camera credential. |
| `POST /api/camera/frame?device_id=…` | Camera bearer token | Binary JPEG HTTPS fallback for inference. |
| `GET /api/shop/status` | Admin | Canonical scenario, inventory, customer cart and available products/zones. |
| `POST /api/shop/configure` | Admin | Explicitly configure/enable/disable the university scenario. |
| `POST /api/shop/frame` | Admin | Browser-source inference frames with stream ID and monotonic sequence. |
| `/api/bottle/*` | Admin | Detector status, explicit image inference and reviewed annotation dataset tools. |
| `/api/presence/*` | Admin | Legacy two-reference calibration and testing. |
| `/api/rtc/view*` | Admin | Open/poll/signal a WebRTC viewer. |
| `/api/rtc/camera/*` | Bound camera token | Poll/send signaling for that device only. |

## WebSockets

- `/ws/camera?device_id=…`: device token in the first auth message, not in the URL. Supports negotiated frame acknowledgments and heartbeat messages.
- `/ws/admin`: admin `AUTH` message followed by server-pushed events.
- `/ws/customer`: session-specific customer transport; follow the shipped client for the credential handshake.

Main event types include `AUTH_OK`, `SHOP_STATE`, `CUSTOMER_ENTERED`, `CART_UPDATED`, `SESSION_CLOSED`, `DEVICE_STATUS`, `ZONES_STATUS`, `EVENT_CREATED` and `CAMERA_WARNING`. A reconnect fetches canonical state instead of trusting local cart deltas.

## WebRTC control is not accounting

The reliable data channel `smartshelf-vision` carries only validated start/stop controls and acknowledgments. The command has a per-viewer request ID and an enabled boolean. An acknowledgment must match that request and device. It does not mutate stock/cart. New authenticated camera frames and the server state machine remain the only vision-driven accounting input.

For examples, read `frontend/assets/js/rtc.js`, `frontend/shop.js` and `scripts/test_shop_tablet_controls.cjs`. Do not paste active tokens into documentation or bug reports.

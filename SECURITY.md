# Security and privacy

This repository is a university prototype, not a certified retail payment system.

- Generate a strong `SECRET_KEY` and admin PIN locally; `.env` and runtime data are ignored by Git.
- Keep SQLite, images uploaded by users, datasets, logs and backups on the store host or a private backup location.
- Camera credentials are signed, time-limited and bound to a device ID. Device auth is distinct from admin auth and customer session auth.
- WebRTC signaling authenticates both roles and isolates sessions/devices. Bounded transient queues and expiration limit retained signaling data.
- The backend receives inference frames into memory. Continuous raw video is not recorded. Explicit product uploads and reviewed training samples are intentionally persisted by their respective features.
- Carts and inventory are server-authoritative; browser/localStorage events cannot create a vision purchase.
- Use exact frontend CORS origins and keep proxy trust disabled unless the proxy boundary is understood.
- Do not expose Windows port 8000 publicly. Keep the selected loopback + HTTPS/WSS tunnel architecture.
- `STORE_OPEN=false` is the default. The university scenario is an explicit demo configuration; no bank payment gateway is part of this workflow.

Public source uses a blank frontend backend origin and contains no owner deployment `.env`, live database, active pairing/customer credentials or private reference-photo archive.

## Reporting

Do not post a working exploit with active credentials or private images in a public issue. Contact the maintainer through the GitHub profile's available contact method to arrange a private report. No dedicated security mailbox or private-reporting setting is claimed to be configured.

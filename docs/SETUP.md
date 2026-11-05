# Installation and demonstration

## Windows: supported owner deployment

1. Clone the repository, or download its source archive, to `C:\SmartShelf`.
2. Run `INSTALL-SMARTSHELF.bat`. The installer expects standard 64-bit Python 3.14, uses winget when Python is missing, creates `.venv`, installs the pinned requirements and creates local configuration/data directories. Inspect scripts before running them on another machine.
3. Keep the generated `.env`, PIN and `SECRET_KEY` private. Default `STORE_OPEN=false` is intentional. Installation does not open a real store or process a bank payment.
4. Run `START-SMARTSHELF.bat`. It launches a single worker on `127.0.0.1:8000`. Keep the window open.
5. Install/sign in to Tailscale using its official Windows distribution. Run `ENABLE-FUNNEL.bat` and complete the displayed Funnel authorization if required.
6. Set the resulting HTTPS backend URL with `scripts/set_public_backend.py`; use its command-line help before supplying your URL. Restart the backend after changing `.env`.
7. Deploy the `frontend/` directory to Vercel, and configure the public backend URL with the web server-settings control or `scripts/set_frontend_backend.py`. Add the exact frontend origin to backend CORS.
8. Run `CHECK-SMARTSHELF.bat`, `CHECK-CONNECTION.bat`, `CHECK-SHOP.bat` and `CHECK-WEBRTC.bat` as appropriate. These diagnostics do not prove real-world detector accuracy.

See [the detailed Windows guide](WINDOWS_LOCAL_DEPLOY_FA.md) and [configuration reference](CONFIGURATION.md).

The public repository intentionally ships `frontend/config.js` with an empty API origin. It never points a new clone at the owner's personal Windows computer. Set your own backend URL. The public source distribution uses locally bundled Vazirmatn; the original private deployment's font binaries are not redistributed.

## Development with an existing Python environment

The recorded Linux QA environment used Python 3.12; Windows installation pins Python 3.14. The Windows dependency lock is in `requirements.txt`; cloud/development packaging is also supplied. This is not a claim that every OS/Python combination has been tested.

```bash
python -m venv .venv
# Activate .venv using your shell's normal activation command.
python -m pip install -r requirements.txt
python scripts/prepare_windows_env.py
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

`prepare_windows_env.py` creates a private local `.env` and secure credentials. Run it locally; do not paste its credentials into an issue. For a custom non-Windows setup, review its Windows-oriented defaults or configure `.env.example` yourself. Keep secrets out of shell history and screenshots.

Open `/admin/` on the local backend and sign in. Local loopback can be used for development; a tablet on another device needs a secure HTTPS origin for camera access.

## Six-step live demo

1. On the tablet, open `/camera/` over HTTPS, grant camera access, and enter the six-digit **device pairing** code generated in the admin Devices tab.
2. In `/shop`, select the paired tablet, open live preview, and place one bottle in its physical location.
3. Capture a still specifically for ROI placement, draw the location, assign a product/price and confirm the ROI. Enable the university scenario. Do not confuse the still ROI image with WebRTC video.
4. Press **Start sending frames**. Wait for the tablet command acknowledgment and increasing server frame counter for that tablet. Stable presence establishes inventory.
5. The customer opens `/enter/` and scans the manager's QR or types the short-lived customer entry code. This code is different from device pairing and admin PIN.
6. Remove and return the bottle. The server confirms stable transitions, updates stock/cart and pushes both screens. End the session through the normal interface.

## Operation

- Keep the tablet page foregrounded. A wake lock is attempted but the OS may still suspend a background page.
- Keep the Windows host online and disable sleep for the demonstration. Autostart registration is an explicit separate action.
- Use the supplied backup tooling for database and uploaded assets; keep backups outside Git.
- Start with both peers on the same non-guest Wi-Fi. Configure TURN only when direct ICE connectivity is insufficient.
- One active customer and one bottle location are the supported accounting scenario. Extra bottles/background detections are not an automatic multi-product inventory system.

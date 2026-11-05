# Troubleshooting by observed symptom

| Symptom | Check / action |
| --- | --- |
| Camera says permission denied after a visible image | Use the current camera page. Old 1.3.1 code had a removed callback misreported as permission denial. Current errors show the actual cause. |
| `NotReadableError` / busy camera | Close other camera applications and other SmartShelf camera tabs. |
| Video playback needs a gesture | Tap Retry to reuse the already granted stream. |
| Page is insecure / camera API unavailable | Open the HTTPS page directly in a current browser, not inside a messenger. |
| WSS remains connecting | Inspect transport status. The authenticated HTTPS fallback should show confirmed delivery. Verify backend URL, tunnel and matching backend version. |
| WebRTC works, Start does nothing | Reopen both `/camera/?v=1.4.1` and `/shop?v=1.4.1`. A new viewer with an old tablet page cannot receive a processing-control acknowledgment. |
| Tablet acknowledges Start but no server frames | Video and inference are separate. Check WSS/HTTPS status on the tablet and the backend's frame counter/device ID. |
| A camera other than the intended tablet is active | Close the other sender; the monitor does not treat another device's frames as success. |
| Preview becomes a still image | Use current WebRTC viewer. ROI capture remains a still by design. |
| WebRTC fails across networks | Test both peers on a non-isolated shared Wi-Fi; configure a suitable TURN server for restrictive NAT. Funnel alone is not a media relay. |
| After pausing inference and closing preview, a new viewer cannot open | Backend 1.4.0 requires a fresh camera frame to select a device. Resume sending on the tablet itself, then reopen preview. |
| Bottle recognized but brand is unknown | Expected for the pretrained generic detector. Assign the product to the location; no brand-trained model is claimed. |
| Inventory does not change immediately | Check scenario enabled/source/ROI; confirmation uses multiple frames and time. `UNKNOWN` or stream gaps break continuity. |
| Customer cannot enter while `STORE_OPEN=false` | Enable the explicit university scenario if that is the intended demo; ordinary store admission remains closed by default. |
| Short code rejected as six digits | Use the current normalization code; Persian/Arabic numerals are supported. Admin PIN, camera pairing and customer entry codes are different credentials. |

When reporting a bug, include OS/browser version, relevant error name, source mode and redacted diagnostic status. Never attach `.env`, active QR codes, device tokens, PINs or a customer database.

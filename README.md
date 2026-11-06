# Photobooth

Raspberry Pi 5 touchscreen photobooth that prints framed 4x6 photos on a Canon SELPHY CP1500. Each print has a QR code that opens a page to download the photo or share it to an Instagram story.

- `booth/` Flask server + full-screen touch UI (runs on the Pi)
- `cloud/` AWS SAM stack: S3 bucket + Lambda behind an HTTP API (upload URLs, share pages, gallery), plus a Rekognition check that keeps flagged photos out of the gallery (moderation page at `/admin`)
- `deploy/` Pi setup script, printer setup, systemd service, Chromium kiosk launcher
- `frames-src/` frame tools (`preview_frames.py`, placeholder frame generator)
- `enclosure/` 3D-printed case for a Bambu X1C: ready-to-print 3MFs (AMS colors set) and STLs, print settings, hardware and assembly steps in `enclosure/README.txt`, fit checks in `cad-check.txt`, and `viewer.html`, a rotatable 3D preview (made just before the last tweak to the tower and paper tunnel)

Setup steps are in [GUIDE.md](GUIDE.md).

Local dev without a Pi: `cd booth && FAKE_CAMERA=1 python3 app.py`, then open http://localhost:8080 in a 1024x600 window. Set `"print_enabled": false` in `booth/config.local.json`.

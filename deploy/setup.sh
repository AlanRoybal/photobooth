#!/usr/bin/env bash
# Run on the Pi from the repo root: bash deploy/setup.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(id -un)"

sudo apt update
sudo apt install -y python3-flask python3-picamera2 python3-pil python3-qrcode python3-requests \
  rpicam-apps cups cups-client cups-bsd cups-filters avahi-daemon curl
if apt-cache show chromium >/dev/null 2>&1; then sudo apt install -y chromium; else sudo apt install -y chromium-browser; fi

sudo usermod -aG lpadmin,video "$USER_NAME"

[ -f "$REPO/booth/config.local.json" ] || cp "$REPO/booth/config.local.example.json" "$REPO/booth/config.local.json"

sed -e "s#__USER__#$USER_NAME#g" -e "s#__REPO__#$REPO#g" "$REPO/deploy/photobooth.service" \
  | sudo tee /etc/systemd/system/photobooth.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now photobooth.service

chmod +x "$REPO/deploy/kiosk.sh"
mkdir -p "$HOME/.config/labwc"
touch "$HOME/.config/labwc/autostart"
grep -q "deploy/kiosk.sh" "$HOME/.config/labwc/autostart" || echo "$REPO/deploy/kiosk.sh &" >> "$HOME/.config/labwc/autostart"

# Desktop autologin, labwc, no screen blanking
sudo raspi-config nonint do_boot_behaviour B4 || true
sudo raspi-config nonint do_wayland W3 || true
sudo raspi-config nonint do_blanking 1 || true

echo "Setup done. Next: bash deploy/setup-printer.sh, edit booth/config.local.json, then sudo reboot"

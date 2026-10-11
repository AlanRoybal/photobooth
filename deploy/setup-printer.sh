#!/usr/bin/env bash
# Run on the Pi once the SELPHY is on the same Wi-Fi: bash deploy/setup-printer.sh
set -euo pipefail
NAME="${1:-SELPHY}"

echo "Looking for the printer on the network..."
URI=""
for _ in $(seq 1 10); do
  URI="$(driverless 2>/dev/null | grep -i selphy | head -n1 || true)"
  [ -n "$URI" ] && break
  sleep 3
done
if [ -z "$URI" ]; then
  echo "No SELPHY found. Make sure it is on the same Wi-Fi as the Pi, then run: driverless; lpinfo -v"
  exit 1
fi
echo "Found: $URI"

sudo lpadmin -p "$NAME" -E -v "$URI" -m everywhere
sudo lpoptions -d "$NAME"
sudo cupsenable "$NAME"
sudo cupsaccept "$NAME"
lpstat -p "$NAME" -l
echo
echo "Paper sizes this printer accepts (look for a Postcard / 4x6 borderless entry):"
lpoptions -p "$NAME" -l | grep -i -E "pagesize|media" || true

#!/usr/bin/env bash
# Started by labwc autostart: waits for the booth server, then opens the UI full screen.
until curl -s -o /dev/null http://localhost:8080/; do sleep 1; done
BROWSER="$(command -v chromium || command -v chromium-browser)"
exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars --incognito --password-store=basic \
  --check-for-update-interval=31536000 --disable-pinch --overscroll-history-navigation=0 \
  --disable-features=Translate --autoplay-policy=no-user-gesture-required \
  http://localhost:8080/

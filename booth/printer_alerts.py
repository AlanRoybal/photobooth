import json
import re
import subprocess
import threading
from pathlib import Path

import requests

PROBLEMS = {
    "media-empty": "out of paper",
    "media-needed": "out of paper",
    "media-jam": "paper jam",
    "input-tray-missing": "paper tray missing",
    "marker-supply-empty": "out of ink",
    "marker-supply-low": "low on ink",
    "marker-supply-missing": "ink cassette missing",
    "door-open": "door open",
}
INK_LOW = "low on ink (by print count)"


def printer_reasons(printer):
    """State reasons from the CUPS queue plus a direct IPP query to the printer (CUPS only refreshes them during a job)."""
    reasons = set()
    info = subprocess.run(["lpstat", "-p", printer, "-l"], capture_output=True, text=True, timeout=10).stdout
    m = re.search(r"Alerts:\s*(.+)", info)
    if m:
        reasons.update(m.group(1).split())
    uri = subprocess.run(["lpstat", "-v", printer], capture_output=True, text=True, timeout=10).stdout
    m = re.search(r"(ipps?://\S+)", uri)
    if m and "._tcp" not in m.group(1):
        try:
            out = subprocess.run(["ipptool", "-tv", m.group(1), "get-printer-attributes.test"],
                                 capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        m = re.search(r"printer-state-reasons \([^)]*\) = (.+)", out)
        if m:
            reasons.update(r.strip() for r in m.group(1).split(","))
    return reasons


def problems(reasons):
    found = set()
    for r in reasons:
        base = re.sub(r"-(error|warning|report)$", "", r)
        if base in PROBLEMS:
            found.add(PROBLEMS[base])
    return found


class PrinterAlerts:
    """Posts to a Discord webhook when the printer runs out of paper/ink, and warns before the ink cassette runs out."""

    def __init__(self, cfg, state_file: Path, every=30):
        self.printer = cfg["printer_name"]
        self.webhook = cfg["discord_webhook_url"]
        self.user_id = str(cfg["discord_ping_user_id"] or "")
        self.per_cassette = int(cfg["ink_prints_per_cassette"])
        self.low_at = int(cfg["ink_low_remaining"])
        self.state_file = state_file
        self.every = every
        self.active = set()
        self.lock = threading.Lock()
        try:
            self.prints_on_cassette = json.loads(state_file.read_text())["prints_on_cassette"]
        except (OSError, ValueError, KeyError):
            self.prints_on_cassette = 0
        if self.webhook:
            threading.Thread(target=self._loop, daemon=True).start()
        else:
            print("discord_webhook_url not set, printer alerts disabled")

    def _save(self):
        self.state_file.write_text(json.dumps({"prints_on_cassette": self.prints_on_cassette}))

    def ink_left(self):
        return max(self.per_cassette - self.prints_on_cassette, 0)

    def ink_replaced(self):
        with self.lock:
            self.prints_on_cassette = 0
            self._save()
            self.active.discard(INK_LOW)

    def printed(self):
        with self.lock:
            self.prints_on_cassette += 1
            self._save()
            left = self.per_cassette - self.prints_on_cassette
        if self.webhook and left == self.low_at:
            self._send(f"Photobooth printer is low on ink: about {left} prints left on this cassette. "
                       f"Have a new RP-108 cassette ready.", ping=True)
            self.active.add(INK_LOW)

    def _send(self, text, ping):
        mention = f"<@{self.user_id}> " if ping and self.user_id else ""
        body = {"content": mention + text, "allowed_mentions": {"users": [self.user_id] if mention else []}}
        try:
            requests.post(self.webhook, json=body, timeout=10).raise_for_status()
        except Exception as e:
            print(f"discord alert failed: {e}")
            return False
        return True

    def check(self):
        now = problems(printer_reasons(self.printer))
        for p in sorted(now - self.active):
            if self._send(f"Photobooth printer: **{p}**. Guests' prints are waiting until it's fixed.", ping=True):
                self.active.add(p)
        for p in sorted((self.active - {INK_LOW}) - now):
            self.active.discard(p)
            self._send(f"Photobooth printer: {p} fixed, printing again.", ping=False)
            if p == "out of ink":
                self.ink_replaced()

    def _loop(self):
        while True:
            try:
                self.check()
            except Exception as e:
                print(f"printer alert check failed: {e}")
            threading.Event().wait(self.every)

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path.home() / "photobooth-data"

DEFAULTS = {
    "title": "Photobooth",
    "port": 8080,
    "countdown_seconds": 3,
    "idle_timeout_seconds": 60,
    "done_screen_seconds": 30,
    "camera_arrow_x_percent": 50,
    "camera_rotate_180": False,
    "camera_ev": 0.0,
    "mirror_preview": True,
    "mirror_photo": True,
    "printer_name": "SELPHY",
    "print_enabled": True,
    "print_options": ["-o", "PageSize=Postcard.Borderless"],
    "print_scale": 0.96,
    "print_gamma": 1.0,
    "share_base_url": "",
    "upload_api_url": "",
    "booth_key": "",
}


def load():
    cfg = dict(DEFAULTS)
    local = ROOT / "config.local.json"
    if local.exists():
        cfg.update(json.loads(local.read_text()))
    return cfg

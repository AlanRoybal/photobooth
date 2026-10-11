import shutil
import threading
import time
from pathlib import Path

import requests

FILES = ("framed.jpg", "thumb.jpg", "story.jpg")


class Uploader:
    """Uploads finished prints to AWS, retrying until the network is available, then deletes the local copy."""

    def __init__(self, prints_dir: Path, api_url: str, booth_key: str):
        self.prints_dir = prints_dir
        self.api_url = api_url.rstrip("/")
        self.booth_key = booth_key
        self.wake = threading.Event()
        if self.api_url:
            threading.Thread(target=self._loop, daemon=True).start()
        else:
            print("upload_api_url not set, uploads disabled")

    def enqueue(self, print_dir: Path):
        (print_dir / "pending").touch()
        self.wake.set()

    def _upload(self, print_dir: Path):
        r = requests.post(
            f"{self.api_url}/upload",
            json={"id": print_dir.name},
            headers={"x-booth-key": self.booth_key},
            timeout=15,
        )
        r.raise_for_status()
        urls = r.json()
        for name in FILES:
            with open(print_dir / name, "rb") as f:
                put = requests.put(urls[name], data=f, headers={"Content-Type": "image/jpeg"}, timeout=60)
            put.raise_for_status()
        shutil.rmtree(print_dir)
        print(f"uploaded {print_dir.name}, local copy deleted")

    def _loop(self):
        while True:
            for marker in sorted(self.prints_dir.glob("*/pending")):
                try:
                    self._upload(marker.parent)
                except Exception as e:
                    print(f"upload {marker.parent.name} failed, will retry: {e}")
                    break
            self.wake.wait(timeout=15)
            self.wake.clear()

import io
import math
import os
import threading
import time

from PIL import Image, ImageDraw, ImageOps

PREVIEW_SIZE = (1024, 576)
STILL_SIZE = (2304, 1296)


class Camera:
    """Live JPEG preview frames plus full-resolution stills from one camera."""

    def __init__(self, rotate_180=False):
        self.lock = threading.Lock()
        self.cond = threading.Condition()
        self.frame = None
        self.picam2 = None
        self.lores = False
        if os.environ.get("FAKE_CAMERA") != "1":
            self._start_picamera(rotate_180)
        threading.Thread(target=self._preview_loop, daemon=True).start()

    def _start_picamera(self, rotate_180):
        try:
            from libcamera import Transform
            from picamera2 import Picamera2
        except ImportError:
            print("picamera2 not available, using fake camera")
            return
        picam2 = Picamera2()
        transform = Transform(hflip=1, vflip=1) if rotate_180 else Transform()
        try:
            config = picam2.create_video_configuration(
                main={"size": STILL_SIZE, "format": "RGB888"},
                lores={"size": PREVIEW_SIZE, "format": "RGB888"},
                transform=transform,
                buffer_count=4,
            )
            picam2.configure(config)
            self.lores = True
        except Exception as e:
            print(f"lores RGB stream unavailable ({e}), scaling main stream for preview")
            config = picam2.create_video_configuration(
                main={"size": STILL_SIZE, "format": "RGB888"},
                transform=transform,
                buffer_count=4,
            )
            picam2.configure(config)
        picam2.start()
        try:
            picam2.set_controls({"AfMode": 2})
        except Exception:
            pass
        self.picam2 = picam2

    def _fake_image(self, size):
        t = time.time()
        img = Image.new("RGB", size)
        d = ImageDraw.Draw(img)
        w, h = size
        for y in range(0, h, 8):
            c = int(127 + 127 * math.sin(t + y / 90))
            d.rectangle([0, y, w, y + 8], fill=(c, 90, 255 - c))
        r = h // 6
        cx = int(w / 2 + w / 4 * math.sin(t))
        d.ellipse([cx - r, h / 2 - r, cx + r, h / 2 + r], fill=(255, 220, 180))
        d.text((20, 20), time.strftime("FAKE CAMERA %H:%M:%S"), fill="white")
        return img

    def _grab(self, want_still=False):
        if self.picam2 is None:
            preview = self._fake_image(PREVIEW_SIZE)
            return preview, (self._fake_image(STILL_SIZE) if want_still else None)
        with self.lock:
            req = self.picam2.capture_request()
            try:
                main = req.make_image("main") if (want_still or not self.lores) else None
                preview = req.make_image("lores") if self.lores else main.resize(PREVIEW_SIZE)
            finally:
                req.release()
        return preview, main

    def _preview_loop(self):
        while True:
            try:
                preview, _ = self._grab()
                buf = io.BytesIO()
                preview.convert("RGB").save(buf, "JPEG", quality=70)
                with self.cond:
                    self.frame = buf.getvalue()
                    self.cond.notify_all()
            except Exception as e:
                print(f"preview error: {e}")
                time.sleep(1)
            if self.picam2 is None:
                time.sleep(1 / 20)

    def mjpeg(self):
        last = None
        while True:
            with self.cond:
                self.cond.wait_for(lambda: self.frame is not last, timeout=2)
                frame = last = self.frame
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

    def capture(self, mirror=False):
        _, still = self._grab(want_still=True)
        still = still.convert("RGB")
        return ImageOps.mirror(still) if mirror else still

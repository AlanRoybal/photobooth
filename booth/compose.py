import json
from pathlib import Path

import qrcode
from PIL import Image, ImageOps

PRINT_SIZE = (1200, 1800)
STORY_SIZE = (1080, 1920)


class Frame:
    def __init__(self, json_path: Path):
        meta = json.loads(json_path.read_text())
        self.id = json_path.stem
        self.name = meta.get("name", self.id)
        self.order = meta.get("order", 100)
        self.photo = meta["photo"]
        self.qr = meta["qr"]
        self.story_bg = meta.get("story_bg", "#000000")
        self.story_photo = meta.get("story_photo")
        self.png = json_path.with_suffix(".png")
        story_png = json_path.with_name(self.id + ".story.png")
        self.story_png = story_png if story_png.exists() and self.story_photo else None


def load_frames(frames_dir: Path):
    frames = [Frame(p) for p in frames_dir.glob("*.json")]
    return sorted((f for f in frames if f.png.exists()), key=lambda f: (f.order, f.id))


def _place_photo(canvas_size, frame_png, photo, rect):
    canvas = Image.new("RGBA", canvas_size, "white")
    fitted = ImageOps.fit(photo, (rect["w"], rect["h"]), Image.LANCZOS)
    canvas.paste(fitted, (rect["x"], rect["y"]))
    overlay = Image.open(frame_png).convert("RGBA").resize(canvas_size)
    return Image.alpha_composite(canvas, overlay).convert("RGB")


def qr_image(url, size):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2, box_size=10)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((size, size), Image.NEAREST)


def framed(photo, frame: Frame):
    return _place_photo(PRINT_SIZE, frame.png, photo, frame.photo)


def with_qr(img, frame: Frame, url):
    out = img.copy()
    out.paste(qr_image(url, frame.qr["size"]), (frame.qr["x"], frame.qr["y"]))
    return out


def for_print(img, scale, gamma=1.0):
    if gamma != 1.0:
        img = img.point([round(255 * (i / 255) ** (1 / gamma)) for i in range(256)] * 3)
    if scale >= 1:
        return img
    page = Image.new("RGB", PRINT_SIZE, "white")
    small = img.resize((round(PRINT_SIZE[0] * scale), round(PRINT_SIZE[1] * scale)), Image.LANCZOS)
    page.paste(small, ((PRINT_SIZE[0] - small.width) // 2, (PRINT_SIZE[1] - small.height) // 2))
    return page


def story(photo, framed_img, frame: Frame):
    if frame.story_png:
        return _place_photo(STORY_SIZE, frame.story_png, photo, frame.story_photo)
    bg = Image.new("RGB", STORY_SIZE, frame.story_bg)
    w = 960
    h = round(framed_img.height * w / framed_img.width)
    bg.paste(framed_img.resize((w, h), Image.LANCZOS), ((STORY_SIZE[0] - w) // 2, (STORY_SIZE[1] - h) // 2))
    return bg

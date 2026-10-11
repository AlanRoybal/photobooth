"""Placeholder frames so the booth works before the real themed frames are made."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "booth" / "frames"
W, H = 1200, 1800
PHOTO = {"x": 80, "y": 120, "w": 1040, "h": 1160}
QR = {"x": 820, "y": 1400, "size": 300}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

STYLES = [
    ("classic", "Classic", "#ffffff", "#111111", "#ffffff"),
    ("midnight", "Midnight", "#14143a", "#ffd400", "#14143a"),
    ("sunset", "Sunset", "#ff6b4a", "#ffffff", "#ff6b4a"),
]


def make(fid, name, bg, fg, story_bg, order):
    img = Image.new("RGBA", (W, H), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([PHOTO["x"], PHOTO["y"], PHOTO["x"] + PHOTO["w"] - 1, PHOTO["y"] + PHOTO["h"] - 1], fill=(0, 0, 0, 0))
    d.text((90, 1400), "PHOTOBOOTH", font=ImageFont.truetype(FONT, 84), fill=fg)
    d.text((94, 1510), name.upper() + " FRAME", font=ImageFont.truetype(FONT, 44), fill=fg)
    d.rounded_rectangle([QR["x"], QR["y"], QR["x"] + QR["size"] - 1, QR["y"] + QR["size"] - 1], 24, outline=fg, width=6)
    d.text((QR["x"] + QR["size"] // 2, QR["y"] + QR["size"] // 2), "LOGO", font=ImageFont.truetype(FONT, 56),
           fill=fg, anchor="mm")
    img.save(OUT / f"{fid}.png")
    (OUT / f"{fid}.json").write_text(json.dumps(
        {"name": name, "order": order, "photo": PHOTO, "qr": QR, "story_bg": story_bg}, indent=2) + "\n")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(STYLES):
        make(*s, order=i)

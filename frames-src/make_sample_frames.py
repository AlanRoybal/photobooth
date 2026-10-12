"""Placeholder frames so the booth works before the real themed frames are made."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "booth" / "frames"
LAYOUTS = {
    "portrait": {"size": (1200, 1800), "photo": {"x": 80, "y": 120, "w": 1040, "h": 1160},
                 "qr": {"x": 820, "y": 1400, "size": 300}, "text": (90, 1400)},
    "landscape": {"size": (1800, 1200), "photo": {"x": 60, "y": 60, "w": 1680, "h": 820},
                  "qr": {"x": 1490, "y": 890, "size": 240}, "text": (80, 920)},
}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

STYLES = [
    ("classic", "Classic", "#ffffff", "#111111", "#ffffff"),
    ("midnight", "Midnight", "#14143a", "#ffd400", "#14143a"),
    ("sunset", "Sunset", "#ff6b4a", "#ffffff", "#ff6b4a"),
]


def make(fid, name, bg, fg, story_bg, order, orientation):
    layout = LAYOUTS[orientation]
    photo, qr, (tx, ty) = layout["photo"], layout["qr"], layout["text"]
    img = Image.new("RGBA", layout["size"], bg)
    d = ImageDraw.Draw(img)
    d.rectangle([photo["x"], photo["y"], photo["x"] + photo["w"] - 1, photo["y"] + photo["h"] - 1], fill=(0, 0, 0, 0))
    d.text((tx, ty), "PHOTOBOOTH", font=ImageFont.truetype(FONT, 84), fill=fg)
    d.text((tx + 4, ty + 110), name.upper() + " FRAME", font=ImageFont.truetype(FONT, 44), fill=fg)
    img.save(OUT / f"{fid}.png")
    (OUT / f"{fid}.json").write_text(json.dumps(
        {"name": name, "order": order, "orientation": orientation, "photo": photo, "qr": qr, "story_bg": story_bg},
        indent=2) + "\n")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(STYLES):
        make(*s, order=i, orientation="portrait")
        make(s[0] + "-landscape", *s[1:], order=i, orientation="landscape")

"""Build the Zero Day mascot frames and home screen from the designer's PNGs.

Usage: python3 frames-src/zeroday/make_frames.py <folder with the Drive PNGs>
Expects "<mascot> portrait photobooth.png" (2400x3600), "<mascot> landscape photobooth.png" (3600x2400)
and "homescreen photobooth.png" (4096x2400). The art is fully opaque, with a soft glow where the photo goes,
so this cuts a feathered hole in the template's photo window and keeps the glow around its edge.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
FRAMES = ROOT / "booth" / "frames"
MASCOTS = ["poyo", "condor", "hyperion", "octans", "remus"]
LAYOUT = {
    "portrait": {"size": (1200, 1800), "photo": {"x": 80, "y": 120, "w": 1040, "h": 1160},
                 "qr": {"x": 820, "y": 1400, "size": 300}},
    "landscape": {"size": (1800, 1200), "photo": {"x": 60, "y": 60, "w": 1680, "h": 820},
                  "qr": {"x": 1490, "y": 890, "size": 240}},
}
FEATHER = 24


def hole(size, p):
    """Alpha: 0 inside the photo window, ramping up to opaque over FEATHER px at its edge."""
    mask = Image.new("L", size, 255)
    inset = FEATHER
    ImageDraw.Draw(mask).rounded_rectangle(
        (p["x"] + inset, p["y"] + inset, p["x"] + p["w"] - inset, p["y"] + p["h"] - inset), radius=FEATHER, fill=0)
    return mask.filter(ImageFilter.GaussianBlur(FEATHER / 2))


def story_bg(img):
    return "#%02x%02x%02x" % img.convert("RGB").resize((1, 1), Image.LANCZOS).getpixel((0, 0))


def main(src):
    src = Path(src)
    for old in ("classic", "midnight", "sunset"):
        for suffix in ("", "-landscape"):
            for ext in (".png", ".json"):
                (FRAMES / f"{old}{suffix}{ext}").unlink(missing_ok=True)
    for order, mascot in enumerate(MASCOTS):
        for orientation, lay in LAYOUT.items():
            art = Image.open(src / f"{mascot} {orientation} photobooth.png").convert("RGBA").resize(lay["size"], Image.LANCZOS)
            alpha = Image.composite(art.getchannel("A"), Image.new("L", lay["size"], 0), hole(lay["size"], lay["photo"]))
            art.putalpha(alpha)
            fid = mascot if orientation == "portrait" else f"{mascot}-landscape"
            art.save(FRAMES / f"{fid}.png", optimize=True)
            meta = {"name": mascot.capitalize(), "order": order, "orientation": orientation,
                    "photo": lay["photo"], "qr": lay["qr"], "story_bg": story_bg(art)}
            (FRAMES / f"{fid}.json").write_text(json.dumps(meta, indent=2) + "\n")
            print(fid)
    home = Image.open(src / "homescreen photobooth.png").convert("RGB").resize((2048, 1200), Image.LANCZOS)
    home.save(ROOT / "booth" / "static" / "home.png", optimize=True)
    print("home.png")


if __name__ == "__main__":
    main(sys.argv[1])

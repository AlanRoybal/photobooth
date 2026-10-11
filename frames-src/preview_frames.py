"""Render every frame in booth/frames with a sample photo to check alignment.

Usage: python3 frames-src/preview_frames.py path/to/sample_photo.jpg
Writes frames-src/previews/<id>.print.jpg and <id>.story.jpg
"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "booth"))
import compose  # noqa: E402

out = ROOT / "frames-src" / "previews"
out.mkdir(exist_ok=True)
photo = Image.open(sys.argv[1]).convert("RGB")
frames = compose.load_frames(ROOT / "booth" / "frames")
for frame in frames:
    framed = compose.framed(photo, frame)
    compose.with_qr(framed, frame, "https://example.com/p/abcd2345").save(out / f"{frame.id}.print.jpg", quality=90)
    compose.story(photo, framed, frame).save(out / f"{frame.id}.story.jpg", quality=90)
    print(f"{frame.id}: ok")
print(f"{len(frames)} frames rendered to {out}")

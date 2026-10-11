"""Blank design templates for the hand-drawn frames and home screen: python3 frames-src/make_templates.py (needs Pillow + DejaVu fonts)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from make_sample_frames import LAYOUTS

OUT = Path(__file__).resolve().parent / "templates"
DPI = 300
SAFE = 70
TRIM = 36
BLUE = (108, 197, 233)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def inches(px):
    return f"{px / DPI:.2f} in"


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def dashed_rect(d, box, color, width=3, dash=18):
    x0, y0, x1, y1 = box
    for x in range(x0, x1, dash * 2):
        d.line([(x, y0), (min(x + dash, x1), y0)], fill=color, width=width)
        d.line([(x, y1), (min(x + dash, x1), y1)], fill=color, width=width)
    for y in range(y0, y1, dash * 2):
        d.line([(x0, y), (x0, min(y + dash, y1))], fill=color, width=width)
        d.line([(x1, y), (x1, min(y + dash, y1))], fill=color, width=width)


def boxes(layout):
    w, h = layout["size"]
    p, q = layout["photo"], layout["qr"]
    return (w, h, (p["x"], p["y"], p["x"] + p["w"] - 1, p["y"] + p["h"] - 1),
            (q["x"], q["y"], q["x"] + q["size"] - 1, q["y"] + q["size"] - 1))


def outlines(layout, base, color):
    """Thin outlines only: canvas edge, safe line, photo window, QR square."""
    w, h, photo, qr = boxes(layout)
    d = ImageDraw.Draw(base)
    d.rectangle([0, 0, w - 1, h - 1], outline=color, width=3)
    dashed_rect(d, (SAFE, SAFE, w - 1 - SAFE, h - 1 - SAFE), color, width=2)
    d.rectangle(photo, outline=color, width=4)
    d.rectangle(qr, outline=color, width=4)
    return base


def blank(layout):
    return outlines(layout, Image.new("RGB", layout["size"], "white"), BLUE)


def overlay(layout):
    return outlines(layout, Image.new("RGBA", layout["size"], (0, 0, 0, 0)), BLUE + (255,))


def guide(orientation, layout):
    w, h, photo, qr = boxes(layout)
    p, q = layout["photo"], layout["qr"]
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 0, w - 1, h - 1], fill=(255, 120, 120, 90))
    d.rectangle([TRIM, TRIM, w - 1 - TRIM, h - 1 - TRIM], fill=(255, 255, 255, 255))
    dashed_rect(d, (SAFE, SAFE, w - 1 - SAFE, h - 1 - SAFE), (220, 60, 60), width=3)
    d.rectangle(photo, fill=(200, 200, 200, 255), outline=(90, 90, 90), width=4)
    d.rectangle(qr, fill=(255, 225, 120, 255), outline=(150, 110, 0), width=4)

    cx, cy = (photo[0] + photo[2]) // 2, (photo[1] + photo[3]) // 2
    d.text((cx, cy - 70), "PHOTO WINDOW", font=font(64, True), fill=(60, 60, 60), anchor="mm")
    d.text((cx, cy + 10), f"{p['w']} x {p['h']} px  ({inches(p['w'])} x {inches(p['h'])})",
           font=font(40), fill=(60, 60, 60), anchor="mm")
    d.text((cx, cy + 70), f"top-left corner at x={p['x']}, y={p['y']} px", font=font(34), fill=(60, 60, 60), anchor="mm")
    d.text((cx, cy + 130), "leave this area empty: the photo goes here", font=font(34), fill=(60, 60, 60), anchor="mm")

    qx, qy = (qr[0] + qr[2]) // 2, (qr[1] + qr[3]) // 2
    d.text((qx, qy - 25), "QR / LOGO", font=font(34, True), fill=(110, 80, 0), anchor="mm")
    d.text((qx, qy + 25), f"{q['size']} px", font=font(30), fill=(110, 80, 0), anchor="mm")

    notes = [
        (f"{orientation.upper()}  {w} x {h} px = {inches(w)} x {inches(h)} @ 300 DPI", True),
        (f"Yellow: QR code, {q['size']} px ({inches(q['size'])}) square at x={q['x']}, y={q['y']}. "
         "Leave it as plain background: the booth puts the QR here on prints and your logo file on downloads and stories.", False),
        ("Red edge (outer 36 px) may be trimmed: fill it with background art, no white.", False),
        (f"Dashed line ({SAFE} px in): keep text, faces and logos inside it.", False),
    ]
    x, y, right = SAFE + 30, photo[3] + 30, qr[0] - 30
    for text, bold in notes:
        f = font(27, bold)
        line = ""
        for word in text.split():
            if line and d.textlength(f"{line} {word}", font=f) > right - x:
                d.text((x, y), line, font=f, fill=(40, 40, 40))
                y += 36
                line = word
            else:
                line = f"{line} {word}".strip()
        d.text((x, y), line, font=f, fill=(40, 40, 40))
        y += 46
    return img


HOME = (1024, 600)
HOME_SCALE = 2
HOME_SAFE = 30
HOME_SIZE = (HOME[0] * HOME_SCALE, HOME[1] * HOME_SCALE)
# Parts of the start screen the booth app draws over the home art, in screen px (includes their idle motion).
HOME_TITLE = (60, 40, 964, 370)
HOME_UI = [
    ("INSTRUCTIONS PANEL", (122, 382, 902, 470), 32),
    ("TAP TO START", (370, 496, 654, 576), 40),
]


def home_outlines(base, color, fill=None):
    s = HOME_SCALE
    w, h = HOME_SIZE
    d = ImageDraw.Draw(base, "RGBA")
    d.rectangle([0, 0, w - 1, h - 1], outline=color, width=4)
    dashed_rect(d, (HOME_SAFE * s, HOME_SAFE * s, w - 1 - HOME_SAFE * s, h - 1 - HOME_SAFE * s), color, width=3)
    for _, box, radius in HOME_UI:
        d.rounded_rectangle([v * s for v in box], radius * s, outline=color, width=4, fill=fill)
    return d


def home_blank():
    img = Image.new("RGB", HOME_SIZE, "white")
    home_outlines(img, BLUE)
    return img


def home_overlay():
    img = Image.new("RGBA", HOME_SIZE, (0, 0, 0, 0))
    home_outlines(img, BLUE + (255,))
    return img


def home_guide():
    img = Image.new("RGB", HOME_SIZE, "white")
    d = home_outlines(img, (90, 60, 140), fill=(36, 31, 56, 255))
    s, w = HOME_SCALE, HOME_SIZE[0]
    for label, box, _ in HOME_UI:
        cx, cy = (box[0] + box[2]) * s // 2, (box[1] + box[3]) * s // 2
        d.text((cx, cy - (20 if label != "TAP TO START" else 0)), label, font=font(40, True), fill=(219, 196, 255), anchor="mm")
    d.text((w // 2, (HOME_UI[0][1][1] + HOME_UI[0][1][3]) * s // 2 + 30), "drawn by the app (the 4 steps)",
           font=font(30), fill=(148, 142, 180), anchor="mm")
    tx0, ty0, tx1, ty1 = [v * s for v in HOME_TITLE]
    dashed_rect(d, (tx0, ty0, tx1, ty1), (255, 46, 230), width=4)
    d.text((w // 2, ty0 + 60), "YOUR TITLE: draw HackUTD here", font=font(52, True), fill=(200, 30, 180), anchor="mm")
    lines = [
        (f"HOME SCREEN  {HOME[0]} x {HOME[1]} px. This template is {w} x {HOME_SIZE[1]} px (2x).", 34, True),
        ("Save your art as home.png at either size.", 30, False),
        ("Pink box: your title. Dark boxes: the app draws these on top of your art, so don't draw instructions or a start button.", 30, False),
        ("The panel is see-through, so art behind it only shows faintly. Keep that area simple.", 30, False),
        ("Guests tap anywhere to start. The art fills the whole screen, so draw to the outer edge.", 30, False),
        (f"Dashed line ({HOME_SAFE} px in): keep faces and logos inside it.", 30, False),
        ("The panel and button are dark purple with a neon glow, so a dark background keeps them readable.", 30, False),
    ]
    y = ty0 + 150
    for text, size, bold in lines:
        d.text((w // 2, y), text, font=font(size, bold), fill=(40, 40, 40), anchor="mm")
        y += size + 16
    return img


def letter_page(orientation, art, label=None):
    """Enlarged copy on US Letter for drawing on paper, with registration marks outside the frame."""
    label = label or f"{orientation.capitalize()} frame"
    page_size = (2550, 3300) if orientation == "portrait" else (3300, 2550)
    page = Image.new("RGB", page_size, "white")
    margin_x, margin_top, margin_bottom = 150, 330, 200
    scale = min((page_size[0] - 2 * margin_x) / art.width, (page_size[1] - margin_top - margin_bottom) / art.height)
    big = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
    x0, y0 = (page_size[0] - big.width) // 2, margin_top
    page.paste(big, (x0, y0))
    d = ImageDraw.Draw(page)
    for mx, my in [(x0, y0), (x0 + big.width, y0), (x0, y0 + big.height), (x0 + big.width, y0 + big.height)]:
        d.line([(mx - 60, my), (mx - 20, my)], fill="black", width=3)
        d.line([(mx + 20, my), (mx + 60, my)], fill="black", width=3)
        d.line([(mx, my - 60), (mx, my - 20)], fill="black", width=3)
        d.line([(mx, my + 20), (mx, my + 60)], fill="black", width=3)
    d.text((page_size[0] // 2, 110), f"{label}, drawn at {big.width / DPI:.1f} x {big.height / DPI:.1f} in",
           font=font(54, True), fill="black", anchor="mm")
    d.text((page_size[0] // 2, 185), "Draw over the light-blue lines (they scan out). Fill art to the outer border. "
           "Scan the whole page at 600 DPI.", font=font(36), fill=(70, 70, 70), anchor="mm")
    return page


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    pdf_pages = []
    for orientation, layout in LAYOUTS.items():
        g, b, o = guide(orientation, layout), blank(layout), overlay(layout)
        g.save(OUT / f"{orientation}-guide.png", dpi=(DPI, DPI))
        b.save(OUT / f"{orientation}-blank.png", dpi=(DPI, DPI))
        o.save(OUT / f"{orientation}-guides-overlay.png", dpi=(DPI, DPI))
        letter_page(orientation, b).save(OUT / f"{orientation}-letter-for-drawing.png", dpi=(DPI, DPI))
        pdf_pages += [g, b, letter_page(orientation, b)]
    hg, hb = home_guide(), home_blank()
    hg.save(OUT / "home-guide.png", dpi=(DPI, DPI))
    hb.save(OUT / "home-blank.png", dpi=(DPI, DPI))
    home_overlay().save(OUT / "home-guides-overlay.png", dpi=(DPI, DPI))
    letter_page("landscape", hb, "Home screen").save(OUT / "home-letter-for-drawing.png", dpi=(DPI, DPI))
    pdf_pages += [hg, letter_page("landscape", hb, "Home screen")]
    pdf_pages[0].save(OUT / "templates-print.pdf", save_all=True, append_images=pdf_pages[1:], resolution=DPI)
    print("wrote", sorted(p.name for p in OUT.iterdir()))

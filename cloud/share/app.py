import base64
import hmac
import html
import json
import os
import re

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

BUCKET = os.environ["BUCKET"]
BOOTH_KEY = os.environ.get("BOOTH_KEY", "")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
EVENT_NAME = os.environ.get("EVENT_NAME", "Photobooth")
INSTAGRAM_HANDLE = re.sub(r"[^A-Za-z0-9._]", "", os.environ.get("INSTAGRAM_HANDLE", ""))
REGION = os.environ.get("AWS_REGION", "us-east-1")
ID_RE = re.compile(r"^[a-z0-9]{6,16}$")
FILES = ("framed.jpg", "thumb.jpg", "story.jpg")
GALLERY_PAGE_SIZE = 48
# Rekognition moderation labels (or their parents) that keep a photo out of the gallery
FLAG_LABELS = {"Explicit", "Explicit Nudity", "Non-Explicit Nudity", "Obstructed Intimate Parts",
               "Graphic Violence", "Visually Disturbing", "Rude Gestures", "Hate Symbols"}
MIN_LABEL_CONFIDENCE = 60
MIN_TEXT_CONFIDENCE = 80
LEET = str.maketrans("013457@$!", "oieastasi")
ASSETS = {}
for _name, _ctype in (("title.png", "image/png"),):
    with open(os.path.join(os.path.dirname(__file__), _name), "rb") as f:
        ASSETS[f"GET /{_name}"] = (_ctype, base64.b64encode(f.read()).decode())
SITE_ASSETS = {}
for _name in os.listdir(os.path.join(os.path.dirname(__file__), "assets")):
    with open(os.path.join(os.path.dirname(__file__), "assets", _name), "rb") as f:
        SITE_ASSETS[_name] = ("image/png" if _name.endswith(".png") else "image/webp", base64.b64encode(f.read()).decode())



def tokens(text):
    return re.sub(r"[^a-z]+", " ", text.lower().translate(LEET)).split()


def load_bad_words():
    words, phrases = set(), set()
    with open(os.path.join(os.path.dirname(__file__), "badwords.txt"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            toks = tokens(line)
            if len(toks) == 1:
                words.add(toks[0])
            elif toks and min(map(len, toks)) > 1:
                phrases.add(" ".join(toks))
    return words, phrases


BAD_WORDS, BAD_PHRASES = load_bad_words()
rekognition = boto3.client("rekognition", region_name=REGION)
s3 = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)


def respond(status, body, content_type="application/json"):
    if not isinstance(body, str):
        body = json.dumps(body)
    return {"statusCode": status, "headers": {"Content-Type": content_type, "Cache-Control": "no-store"}, "body": body}


def key(photo_id, name):
    return f"prints/{photo_id}/{name}"


def upload(event):
    sent = (event.get("headers") or {}).get("x-booth-key", "")
    if not BOOTH_KEY or not hmac.compare_digest(sent.encode(), BOOTH_KEY.encode()):
        return respond(403, {"error": "forbidden"})
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    photo_id = str(json.loads(raw).get("id", ""))
    if not ID_RE.match(photo_id):
        return respond(400, {"error": "bad id"})
    urls = {
        name: s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET, "Key": key(photo_id, name), "ContentType": "image/jpeg"},
            ExpiresIn=600,
        )
        for name in FILES
    }
    return respond(200, urls)


def image(photo_id, name, query):
    if not ID_RE.match(photo_id) or name not in FILES:
        return respond(404, {"error": "not found"})
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key(photo_id, name))
    except ClientError:
        return respond(404, {"error": "not found"})
    headers = {"Content-Type": "image/jpeg", "Cache-Control": "public, max-age=31536000, immutable"}
    if query.get("download"):
        filename = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{EVENT_NAME}-{photo_id}").strip("-")
        headers["Content-Disposition"] = f'attachment; filename="{filename}.jpg"'
    return {"statusCode": 200, "headers": headers, "isBase64Encoded": True,
            "body": base64.b64encode(obj["Body"].read()).decode()}


def page(photo_id):
    if not ID_RE.match(photo_id):
        return respond(404, PENDING.replace("{title}", "Not found"), "text/html")
    title = html.escape(EVENT_NAME)
    try:
        s3.head_object(Bucket=BUCKET, Key=key(photo_id, "story.jpg"))
    except ClientError:
        return respond(200, PENDING.replace("{title}", title), "text/html")
    body = (
        PAGE.replace("{title}", title)
        .replace("{photo}", f"/{photo_id}/framed.jpg")
        .replace("{download}", f"/{photo_id}/framed.jpg?download=1")
        .replace("{story}", json.dumps(f"/{photo_id}/story.jpg"))
        .replace("{filename}", json.dumps(f"story-{photo_id}.jpg"))
        .replace("{handle}", json.dumps(f"@{INSTAGRAM_HANDLE}" if INSTAGRAM_HANDLE else ""))
    )
    return respond(200, body, "text/html")


def scan():
    """(id, file names) of finished uploads (story.jpg is uploaded last), newest first."""
    files, done = {}, {}
    for page_ in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="prints/"):
        for obj in page_.get("Contents", []):
            parts = obj["Key"].split("/")
            if len(parts) != 3:
                continue
            files.setdefault(parts[1], set()).add(parts[2])
            if parts[2] == "story.jpg":
                done[parts[1]] = obj["LastModified"]
    return [(i, files[i]) for i in sorted(done, key=done.get, reverse=True)]


def status(names):
    """Moderation verdict, stored as an empty-ish marker object next to the photo."""
    return "hidden" if "hidden" in names else "visible" if "visible" in names else "pending"


def thumb(photo_id, names):
    return f"/{photo_id}/{'thumb' if 'thumb.jpg' in names else 'framed'}.jpg"


def list_photos():
    """Finished uploads that passed moderation, newest first."""
    return [{"id": i, "src": thumb(i, n)} for i, n in scan() if status(n) == "visible"]


def gallery_photos(query):
    try:
        start = max(0, int(query.get("start", 0)))
    except ValueError:
        start = 0
    photos = list_photos()
    end = start + GALLERY_PAGE_SIZE
    return respond(200, {"photos": photos[start:end], "next": end if end < len(photos) else None})


def profanity(lines):
    found = set()
    for line in lines:
        toks = tokens(line)
        found |= BAD_WORDS.intersection(toks)
        joined = f" {' '.join(toks)} "
        found |= {p for p in BAD_PHRASES if f" {p} " in joined}
        run = ""
        for t in toks + [""]:  # catch spelled-out words like "F U C K"
            if len(t) == 1:
                run += t
            else:
                if run in BAD_WORDS:
                    found.add(run)
                run = ""
    return sorted(found)


def set_status(photo_id, visible, by, reasons=()):
    on, off = ("visible", "hidden") if visible else ("hidden", "visible")
    s3.put_object(Bucket=BUCKET, Key=key(photo_id, on), ContentType="application/json",
                  Body=json.dumps({"by": by, "reasons": list(reasons)}).encode())
    s3.delete_object(Bucket=BUCKET, Key=key(photo_id, off))
    return {"id": photo_id, "status": on, "by": by, "reasons": list(reasons)}


def moderate(photo_id):
    image_ = {"S3Object": {"Bucket": BUCKET, "Name": key(photo_id, "framed.jpg")}}
    labels = rekognition.detect_moderation_labels(Image=image_, MinConfidence=MIN_LABEL_CONFIDENCE)["ModerationLabels"]
    reasons = sorted({lb["Name"] for lb in labels if {lb["Name"], lb.get("ParentName")} & FLAG_LABELS})
    lines = [t["DetectedText"] for t in rekognition.detect_text(Image=image_)["TextDetections"]
             if t["Type"] == "LINE" and t["Confidence"] >= MIN_TEXT_CONFIDENCE]
    reasons += [f"Text: {w}" for w in profanity(lines)]
    result = set_status(photo_id, not reasons, "auto", reasons)
    print(json.dumps(result))
    return result


def photo_files(photo_id):
    resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"prints/{photo_id}/")
    return {obj["Key"].split("/")[2] for obj in resp.get("Contents", [])}


def moderate_handler(event, context):
    """Runs on S3 "Object Created" events for story.jpg, or directly with {"backfill": true}."""
    if event.get("backfill"):
        ids = [i for i, n in scan() if status(n) == "pending"]
    else:
        photo_id = event["detail"]["object"]["key"].split("/")[1]
        ids = [photo_id] if ID_RE.match(photo_id) and status(photo_files(photo_id)) == "pending" else []
    for photo_id in ids:
        moderate(photo_id)
    return {"moderated": ids}


def is_admin(event):
    sent = (event.get("headers") or {}).get("x-admin-key", "")
    return bool(ADMIN_KEY) and hmac.compare_digest(sent.encode(), ADMIN_KEY.encode())


def admin_photos():
    photos = []
    for i, n in scan():
        p = {"id": i, "src": thumb(i, n), "status": status(n), "by": "", "reasons": []}
        if p["status"] == "hidden":
            try:
                p.update(json.loads(s3.get_object(Bucket=BUCKET, Key=key(i, "hidden"))["Body"].read()))
            except (ClientError, ValueError):
                pass
        photos.append(p)
    return respond(200, {"photos": photos})


def admin_set(photo_id, event):
    if not ID_RE.match(photo_id):
        return respond(404, {"error": "not found"})
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    return respond(200, set_status(photo_id, bool(json.loads(raw).get("visible")), "admin"))


def handler(event, context):
    route = event.get("routeKey", "")
    params = {k: v.lower() if k == "id" else v for k, v in (event.get("pathParameters") or {}).items()}
    query = event.get("queryStringParameters") or {}
    if route == "POST /upload":
        return upload(event)
    if route == "GET /":
        return respond(200, GALLERY.replace("{title}", html.escape(EVENT_NAME)), "text/html")
    if route == "GET /assets/{name}" and params.get("name") in SITE_ASSETS:
        route = params["name"]
    if route in ASSETS or route in SITE_ASSETS:
        ctype, body = ASSETS.get(route) or SITE_ASSETS[route]
        return {"statusCode": 200, "isBase64Encoded": True, "body": body,
                "headers": {"Content-Type": ctype, "Cache-Control": "public, max-age=86400"}}
    if route == "GET /api/photos":
        return gallery_photos(query)
    if route == "GET /admin":
        return respond(200, ADMIN.replace("{title}", html.escape(EVENT_NAME)), "text/html")
    if route.startswith(("GET /api/admin/", "POST /api/admin/")) and not is_admin(event):
        return respond(403, {"error": "forbidden"})
    if route == "GET /api/admin/photos":
        return admin_photos()
    if route == "POST /api/admin/photos/{id}":
        return admin_set(params.get("id", ""), event)
    if route == "GET /{id}/{file}":
        return image(params.get("id", ""), params.get("file", ""), query)
    if route in ("GET /{id}", "GET /p/{id}"):
        return page(params.get("id", ""))
    return respond(404, {"error": "not found"})


STYLE = """
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#000000">
<link rel="preconnect" href="https://api.fontshare.com" crossorigin>
<link rel="stylesheet" href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900&display=swap">
<style>
  :root { --fg: #f4f2ff; --muted: #8b93a1; --hairline: #232a36; --surface: #0e011f; --accent: #7828ff;
    --soft: #dbc4ff; --magenta: #ff2ee6; --ease: cubic-bezier(.16, 1, .3, 1);
    --notch: polygon(12px 0, 100% 0, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%, 0 12px); }
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  body { position: relative; isolation: isolate; margin: 0; min-height: 100vh; color: var(--fg); text-align: center; padding: 32px 20px 48px;
    font-family: satoshi, Arial, sans-serif; -webkit-font-smoothing: antialiased; background: #000
    radial-gradient(120% 55% at 50% 0%, #2a0a5c 0%, #0e011f 45%, #000 85%) no-repeat; }
  .banner { position: relative; max-width: 420px; margin: 0 auto 22px; }
  .banner img { display: block; width: 100%; }
  .sign-echo { position: absolute; inset: 0; opacity: 0; pointer-events: none; clip-path: inset(36% 0 43%);
    filter: drop-shadow(-3px 0 #ff2ee6) brightness(1.35) saturate(1.5); animation: sign-signal 5s step-end 3.1s infinite; }
  @keyframes sign-signal { 0%, 5%, to { opacity: 0; transform: none; }
    1% { opacity: .85; clip-path: inset(30% 0 40%); transform: translate(1.1%); } 2.5% { opacity: 0; }
    3.5% { opacity: .7; clip-path: inset(55% 0 20%); transform: translate(-.85%); } }
  .scene { position: absolute; inset: 0 0 auto; height: min(80vh, 760px); z-index: -1; pointer-events: none; opacity: .6;
    background: url(/assets/skyline.webp) 50% 0 / cover no-repeat;
    -webkit-mask-image: linear-gradient(#000 25%, transparent); mask-image: linear-gradient(#000 25%, transparent); }
  .frame { position: relative; display: block; width: 100%; max-width: 420px; margin: 0 auto; padding: 2px;
    background: linear-gradient(135deg, #ff2ee6, #7828ff 50%, #2ee6ff);
    box-shadow: 0 0 32px rgba(120,40,255,.5), 0 0 80px rgba(255,46,230,.16); }
  .frame img { display: block; width: 100%; background: var(--surface); }
  .btn { position: relative; display: flex; align-items: center; justify-content: center; width: 100%; max-width: 420px;
    height: 52px; margin: 14px auto 0; padding: 0 20px; border: 0; cursor: pointer; text-decoration: none;
    font: 500 13px/1.3 satoshi, Arial, sans-serif; letter-spacing: .1em; text-transform: uppercase; color: #fff;
    clip-path: var(--notch); transition: opacity .18s, transform .12s var(--ease); -webkit-tap-highlight-color: transparent; }
  .btn span { position: relative; }
  .btn:hover { opacity: .9; }
  .btn:active { transform: scale(.98); }
  .ig { background: var(--accent); }
  .ig:disabled { opacity: .4; cursor: default; }
  .dl, .gal { background: rgba(219,196,255,.4); color: var(--soft); }
  .gal { background: var(--hairline); color: var(--muted); }
  .dl::before, .gal::before { content: ""; position: absolute; inset: 1px; background: var(--surface);
    clip-path: polygon(11.6px 0, 100% 0, 100% calc(100% - 11.6px), calc(100% - 11.6px) 100%, 0 100%, 0 11.6px); }
  .gal::before { background: #000; }
  p { color: var(--muted); font-size: 13px; line-height: 1.6; letter-spacing: .04em; max-width: 420px; margin: 18px auto 0; }
  #tagline { margin: 0 auto 18px; color: var(--soft); font-size: 17px; line-height: 1.35; text-wrap: balance; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
  #tagline b { color: var(--magenta); }
  .skeleton { background-color: var(--surface); border: 1px solid var(--hairline); border-radius: 3px;
    background-image: linear-gradient(90deg, #fff0 0%, #ffffff0b 50%, #fff0 100%); background-repeat: no-repeat;
    background-size: 200% 100%; animation: sweep 1.4s ease-in-out infinite; }
  .reveal { animation: reveal .7s var(--ease) var(--d, 0s) both; }
  @keyframes reveal { from { opacity: 0; filter: blur(4px); transform: translateY(14px); } }
  @keyframes sweep { 0% { background-position: 150% 0; } to { background-position: -50% 0; } }
  .rail { position: relative; height: 52px; max-width: 520px; margin: 40px auto 0; overflow: hidden;
    border-bottom: 2px solid rgba(219,196,255,.22); }
  .rail img { position: absolute; bottom: 4px; left: -340px; height: 44px; animation: ride 11s linear infinite; }
  @keyframes ride { to { left: 100%; } }
  .lineart { display: block; width: 100%; max-width: 900px; margin: 0 auto; opacity: .3; mix-blend-mode: screen; }
  @media (prefers-reduced-motion: reduce) { .reveal, .skeleton, .sign-echo, .rail img, .peek img { animation: none !important; } }
</style>
"""

PENDING = """<!doctype html><html><head><meta charset="utf-8"><link rel="icon" type="image/png" href="/assets/favicon.png"><link rel="apple-touch-icon" href="/assets/apple-touch-icon.png"><title>{title}</title>
<meta http-equiv="refresh" content="8">""" + STYLE + """</head><body>
<div class="scene" aria-hidden="true"></div>
<div class="banner reveal"><img src="/title.png" alt="{title}"><img class="sign-echo" src="/title.png" alt="" aria-hidden="true"></div>
<div class="frame skeleton reveal" style="--d:90ms; aspect-ratio: 2 / 3"></div>
<p class="reveal" style="--d:.18s">Your photo is on its way. This page will refresh by itself in a few seconds.</p>
</body></html>"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"><link rel="icon" type="image/png" href="/assets/favicon.png"><link rel="apple-touch-icon" href="/assets/apple-touch-icon.png"><title>{title}</title>""" + STYLE + """</head><body>
<div class="scene" aria-hidden="true"></div>
<div class="banner reveal"><img src="/title.png" alt="{title}"><img class="sign-echo" src="/title.png" alt="" aria-hidden="true"></div>
<p id="tagline" class="reveal" style="--d:45ms" hidden>Share to your story and tag us! <b id="handle"></b></p>
<div class="stage reveal" style="--d:90ms">
  <div class="peek" aria-hidden="true"><img src="/assets/poyo.webp" alt=""></div>
  <div class="frame"><img src="{photo}" alt="Your photobooth picture"></div>
</div>
<button id="share" class="btn ig reveal" style="--d:.18s" disabled><span>Share to Instagram Story</span></button>
<a class="btn dl reveal" style="--d:.22s" href="{download}"><span>Download photo</span></a>
<a class="btn gal reveal" style="--d:.27s" href="/"><span>See everyone's photos</span></a>
<div class="rail" aria-hidden="true"><img src="/assets/train.webp" alt=""></div>
<img class="lineart" src="/assets/lineart.webp" alt="" aria-hidden="true">
<style>
  .stage { position: relative; max-width: 420px; margin: calc(min(100vw - 40px, 420px) * .2) auto 0; }
  .peek { position: absolute; right: 7%; bottom: 100%; width: 30%; aspect-ratio: 500 / 358; overflow: hidden; margin-bottom: -1px; }
  .peek img { display: block; width: 100%; animation: peek .9s var(--ease) .6s both; }
  @keyframes peek { from { transform: translateY(102%); } }
  .rail { margin-top: 36px; }
</style>
<script>
  const shareBtn = document.getElementById("share");
  let file = null;
  fetch({story})
    .then((r) => r.blob())
    .then((b) => {
      file = new File([b], {filename}, { type: "image/jpeg" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        shareBtn.disabled = false;
      }
    })
    .catch(() => {});
  const handle = {handle};
  if (handle) {
    document.getElementById("handle").textContent = handle;
    document.getElementById("tagline").hidden = false;
  }
  shareBtn.addEventListener("click", () => {
    navigator.share({ files: [file] }).catch(() => {});
  });
</script>
</body></html>"""

GALLERY = """<!doctype html><html><head><meta charset="utf-8"><link rel="icon" type="image/png" href="/assets/favicon.png"><link rel="apple-touch-icon" href="/assets/apple-touch-icon.png"><title>{title}</title>""" + STYLE + """
<style>
  body { padding: 28px 12px 44px; }
  .banner { max-width: 640px; margin-bottom: 10px; }
  .hero { max-width: 1100px; margin: 0 auto; }
  .kicker { margin: 0 auto; color: var(--soft); font-size: 15px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
  .crew { display: block; width: min(50vw, 230px); margin: 18px auto 0; filter: drop-shadow(0 0 24px rgba(120,40,255,.45)); }
  .rail { margin: 6px auto 28px; max-width: 1100px; }
  @media (min-width: 820px) {
    .hero { display: grid; grid-template-columns: 1fr auto; align-items: end; gap: 32px; text-align: left; }
    .hero .banner { margin: 0 0 12px; } .hero .kicker { margin: 0; font-size: 17px; }
    .crew { width: 300px; margin: 0; }
  }
  #grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; max-width: 1100px; margin: 0 auto; }
  @media (min-width: 820px) { #grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 18px; } }
  #grid > * { aspect-ratio: 2 / 3; }
  #grid a { display: block; padding: 2px; background: linear-gradient(135deg, rgba(255,46,230,.55), rgba(120,40,255,.55) 50%, rgba(46,230,255,.55));
    transition: box-shadow .3s, transform .12s var(--ease); }
  #grid a:hover, #grid a:focus-visible { box-shadow: 0 0 26px rgba(255,46,230,.45); outline: none; transform: translateY(-2px); }
  #grid a:active { transform: scale(.98); }
  #grid { grid-auto-flow: dense; }
  #grid a.wide { grid-column: span 2; aspect-ratio: auto; }
  #grid img { display: block; width: 100%; height: 100%; object-fit: contain; background: var(--surface); }
  #status { margin-top: 26px; font-size: 12px; letter-spacing: .1em; text-transform: uppercase; }
</style></head><body>
<div class="scene" aria-hidden="true"></div>
<header class="hero">
  <div>
    <div class="banner reveal"><img src="/title.png" alt="{title}"><img class="sign-echo" src="/title.png" alt="" aria-hidden="true"></div>
    <p class="kicker reveal" style="--d:60ms">Everyone's booth photos</p>
  </div>
  <img class="crew reveal" style="--d:120ms" src="/assets/mascots.webp" alt="Poyo, Condor, Hyperion, Octans and Remus">
</header>
<div class="rail" aria-hidden="true"><img src="/assets/train.webp" alt=""></div>
<div id="grid"></div>
<p id="status">Loading photos...</p>
<img class="lineart" src="/assets/lineart.webp" alt="" aria-hidden="true" style="margin-top: 36px">
<script>
  const grid = document.getElementById("grid");
  const status = document.getElementById("status");
  for (let i = 0; i < 8; i++) {
    const s = document.createElement("div");
    s.className = "skeleton placeholder";
    grid.appendChild(s);
  }
  let next = 0, loading = false;
  async function more() {
    if (loading || next === null) return;
    loading = true;
    try {
      const data = await (await fetch("/api/photos?start=" + next)).json();
      grid.querySelectorAll(".placeholder").forEach((s) => s.remove());
      data.photos.forEach((p, i) => {
        const a = document.createElement("a");
        a.href = "/" + p.id;
        a.className = "reveal";
        a.style.setProperty("--d", (i % 12) * 40 + "ms");
        const img = document.createElement("img");
        img.src = p.src;
        img.loading = "lazy";
        img.alt = "";
        img.onload = () => { if (img.naturalWidth > img.naturalHeight) a.classList.add("wide"); };
        a.appendChild(img);
        grid.appendChild(a);
      });
      next = data.next;
      status.textContent = grid.children.length ? (next === null ? "" : "Loading more...") : "No photos yet. Check back soon!";
    } catch (e) {
      grid.querySelectorAll(".placeholder").forEach((s) => s.remove());
      status.textContent = "Couldn't load photos. Pull down to refresh.";
    }
    loading = false;
  }
  new IntersectionObserver((entries) => { if (entries[0].isIntersecting) more(); }).observe(status);
  more();
</script>
</body></html>"""

ADMIN = """<!doctype html><html><head><meta charset="utf-8"><link rel="icon" type="image/png" href="/assets/favicon.png"><link rel="apple-touch-icon" href="/assets/apple-touch-icon.png"><title>Admin - {title}</title>
<meta name="robots" content="noindex">""" + STYLE + """
<style>
  body { padding: 28px 12px 44px; }
  h1 { margin: 0; font-size: 15px; letter-spacing: .14em; text-transform: uppercase; }
  #login { max-width: 420px; margin: 32px auto 0; }
  #login input { width: 100%; height: 52px; padding: 0 16px; border: 1px solid var(--hairline); background: var(--surface);
    color: var(--fg); font: 15px satoshi, Arial, sans-serif; }
  .tabs { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin: 16px 0 22px; }
  .tabs button, .card button { height: 36px; padding: 0 14px; border: 0; cursor: pointer; color: var(--fg); background: var(--hairline);
    font: 500 12px satoshi, Arial, sans-serif; letter-spacing: .1em; text-transform: uppercase; }
  .tabs button.on { background: var(--accent); }
  #grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; max-width: 1100px; margin: 0 auto; }
  .card { padding: 6px; border: 1px solid var(--hairline); background: var(--surface); text-align: left; }
  .card img { display: block; width: 100%; aspect-ratio: 2 / 3; object-fit: contain; background: #000; }
  .card.hidden img { opacity: .35; filter: grayscale(1); }
  .tag { margin: 8px 2px 2px; font-size: 11px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
  .visible .tag { color: #5be37d; } .hidden .tag { color: var(--magenta); } .pending .tag { color: var(--muted); }
  .why { min-height: 1.4em; margin: 0 2px 8px; color: var(--muted); font-size: 12px; }
  .card button { width: 100%; }
  .card.visible button { background: #5a1030; }
  .card button:disabled { opacity: .5; cursor: default; }
</style></head><body>
<h1>Gallery moderation</h1>
<form id="login" hidden>
  <input id="password" type="password" placeholder="Admin password" autocomplete="current-password">
  <button class="btn ig"><span>Sign in</span></button>
  <p id="error"></p>
</form>
<div id="app" hidden>
  <div class="tabs" id="tabs"></div>
  <div id="grid"></div>
  <p id="status"></p>
</div>
<script>
  const STORE = "photobooth-admin-key";
  const FILTERS = { all: "All", visible: "In gallery", hidden: "Hidden", pending: "Checking" };
  const LABELS = { visible: "In gallery", hidden: "Hidden", pending: "Checking..." };
  let key = localStorage.getItem(STORE) || "", photos = [], filter = "all";
  const $ = (id) => document.getElementById(id);

  function signOut(message) {
    localStorage.removeItem(STORE);
    key = "";
    $("app").hidden = true;
    $("login").hidden = false;
    $("error").textContent = message || "";
  }
  async function api(path, options = {}) {
    const r = await fetch(path, { ...options, headers: { "x-admin-key": key, "Content-Type": "application/json" } });
    if (r.status === 403) { signOut("Wrong password."); throw new Error("forbidden"); }
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }
  async function load() {
    if (!key) return signOut();
    try {
      photos = (await api("/api/admin/photos")).photos;
      $("login").hidden = true;
      $("app").hidden = false;
      $("status").textContent = "";
      render();
    } catch (e) {
      if (key) $("status").textContent = "Couldn't load photos. Retrying...";
    }
  }
  function render() {
    $("tabs").replaceChildren(...Object.entries(FILTERS).map(([f, label]) => {
      const b = document.createElement("button");
      const n = f === "all" ? photos.length : photos.filter((p) => p.status === f).length;
      b.textContent = label + " (" + n + ")";
      b.className = f === filter ? "on" : "";
      b.onclick = () => { filter = f; render(); };
      return b;
    }));
    const shown = photos.filter((p) => filter === "all" || p.status === filter);
    $("grid").replaceChildren(...shown.map((p) => {
      const card = document.createElement("div");
      card.className = "card " + p.status;
      const link = document.createElement("a");
      link.href = "/" + p.id;
      link.target = "_blank";
      const img = document.createElement("img");
      img.src = p.src;
      img.loading = "lazy";
      img.alt = "";
      link.appendChild(img);
      const tag = document.createElement("div");
      tag.className = "tag";
      tag.textContent = LABELS[p.status];
      const why = document.createElement("div");
      why.className = "why";
      why.textContent = p.reasons.length ? p.reasons.join(", ") : p.by === "admin" ? "Changed by admin" : "";
      const button = document.createElement("button");
      button.textContent = p.status === "visible" ? "Hide" : "Show in gallery";
      button.onclick = async () => {
        button.disabled = true;
        try {
          Object.assign(p, await api("/api/admin/photos/" + p.id, {
            method: "POST", body: JSON.stringify({ visible: p.status !== "visible" }) }));
          render();
        } catch (e) { button.disabled = false; }
      };
      card.append(link, tag, why, button);
      return card;
    }));
    $("status").textContent = shown.length ? "" : "No photos here.";
  }
  $("login").onsubmit = (e) => {
    e.preventDefault();
    key = $("password").value;
    localStorage.setItem(STORE, key);
    load();
  };
  load();
  setInterval(() => { if (key && !document.hidden) load(); }, 20000);
</script>
</body></html>"""

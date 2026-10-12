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
BOOTH_KEY = os.environ["BOOTH_KEY"]
EVENT_NAME = os.environ.get("EVENT_NAME", "Photobooth")
INSTAGRAM_HANDLE = re.sub(r"[^A-Za-z0-9._]", "", os.environ.get("INSTAGRAM_HANDLE", ""))
REGION = os.environ.get("AWS_REGION", "us-east-1")
ID_RE = re.compile(r"^[a-z0-9]{6,16}$")
FILES = ("framed.jpg", "thumb.jpg", "story.jpg")
GALLERY_PAGE_SIZE = 48
ASSETS = {}
for _name, _ctype in (("title.png", "image/png"),):
    with open(os.path.join(os.path.dirname(__file__), _name), "rb") as f:
        ASSETS[f"GET /{_name}"] = (_ctype, base64.b64encode(f.read()).decode())

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
    if not hmac.compare_digest(sent.encode(), BOOTH_KEY.encode()):
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


def list_photos():
    """Finished uploads (story.jpg is uploaded last), newest first."""
    photos, has_thumb = {}, set()
    for page_ in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="prints/"):
        for obj in page_.get("Contents", []):
            parts = obj["Key"].split("/")
            if len(parts) != 3:
                continue
            if parts[2] == "story.jpg":
                photos[parts[1]] = obj["LastModified"]
            elif parts[2] == "thumb.jpg":
                has_thumb.add(parts[1])
    ordered = sorted(photos, key=photos.get, reverse=True)
    return [{"id": i, "src": f"/{i}/{'thumb' if i in has_thumb else 'framed'}.jpg"} for i in ordered]


def gallery_photos(query):
    try:
        start = max(0, int(query.get("start", 0)))
    except ValueError:
        start = 0
    photos = list_photos()
    end = start + GALLERY_PAGE_SIZE
    return respond(200, {"photos": photos[start:end], "next": end if end < len(photos) else None})


def handler(event, context):
    route = event.get("routeKey", "")
    params = {k: v.lower() if k == "id" else v for k, v in (event.get("pathParameters") or {}).items()}
    query = event.get("queryStringParameters") or {}
    if route == "POST /upload":
        return upload(event)
    if route == "GET /":
        return respond(200, GALLERY.replace("{title}", html.escape(EVENT_NAME)), "text/html")
    if route in ASSETS:
        ctype, body = ASSETS[route]
        return {"statusCode": 200, "isBase64Encoded": True, "body": body,
                "headers": {"Content-Type": ctype, "Cache-Control": "public, max-age=86400"}}
    if route == "GET /api/photos":
        return gallery_photos(query)
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
  body { margin: 0; min-height: 100vh; color: var(--fg); text-align: center; padding: 32px 20px 48px;
    font-family: satoshi, Arial, sans-serif; -webkit-font-smoothing: antialiased; background: #000
    radial-gradient(120% 55% at 50% 0%, #2a0a5c 0%, #0e011f 45%, #000 85%) no-repeat; }
  h1 { font-weight: 900; font-size: clamp(1.75rem, 7vw, 2.5rem); line-height: 1; letter-spacing: -.02em;
    text-transform: uppercase; margin: 6px 0 26px; }
  .frame { display: block; width: 100%; max-width: 420px; margin: 0 auto; padding: 1px; background: rgba(255,255,255,.14); }
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
  #tagline { color: var(--soft); font-size: 12px; letter-spacing: .1em; text-transform: uppercase; }
  #tagline b { color: var(--magenta); font-weight: 700; }
  .skeleton { background-color: var(--surface); border: 1px solid var(--hairline); border-radius: 3px;
    background-image: linear-gradient(90deg, #fff0 0%, #ffffff0b 50%, #fff0 100%); background-repeat: no-repeat;
    background-size: 200% 100%; animation: sweep 1.4s ease-in-out infinite; }
  .reveal { animation: reveal .7s var(--ease) var(--d, 0s) both; }
  h1.reveal { animation: reveal .7s var(--ease) both, signal 1s ease-out both; }
  @keyframes reveal { from { opacity: 0; filter: blur(4px); transform: translateY(14px); } }
  @keyframes signal { 0% { text-shadow: -2px 0 #73ebff8c, 2px 0 #ff2ee699; } 45% { text-shadow: 0 0 16px #ff2ee647; } to { text-shadow: 0 0 #0000; } }
  @keyframes sweep { 0% { background-position: 150% 0; } to { background-position: -50% 0; } }
  @media (prefers-reduced-motion: reduce) { .reveal, h1.reveal, .skeleton, .sign-echo { animation: none !important; } }
</style>
"""

PENDING = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<meta http-equiv="refresh" content="8">""" + STYLE + """</head><body>
<h1 class="reveal">{title}</h1>
<div class="frame skeleton reveal" style="--d:90ms; aspect-ratio: 2 / 3"></div>
<p class="reveal" style="--d:.18s">Your photo is on its way. This page will refresh by itself in a few seconds.</p>
</body></html>"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>""" + STYLE + """</head><body>
<h1 class="reveal">{title}</h1>
<div class="frame reveal" style="--d:90ms"><img src="{photo}" alt="Your photobooth picture"></div>
<button id="share" class="btn ig reveal" style="--d:.18s" disabled><span>Share to Instagram Story</span></button>
<a class="btn dl reveal" style="--d:.22s" href="{download}"><span>Download photo</span></a>
<a class="btn gal reveal" style="--d:.27s" href="/"><span>View gallery</span></a>
<p id="howto">Tap Share to Instagram Story, pick Instagram, then Story.</p>
<p id="tagline" hidden>Share to your story and tag us! <b id="handle"></b></p>
<script>
  const shareBtn = document.getElementById("share");
  let file = null;
  fetch({story})
    .then((r) => r.blob())
    .then((b) => {
      file = new File([b], {filename}, { type: "image/jpeg" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        shareBtn.disabled = false;
      } else {
        fallback();
      }
    })
    .catch(fallback);
  function fallback() {
    document.getElementById("howto").hidden = true;
  }
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

GALLERY = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>""" + STYLE + """
<style>
  body { padding: 28px 12px 44px; }
  .banner { position: relative; max-width: 720px; margin: 0 auto 28px; }
  .banner img { display: block; width: 100%; }
  .sign-echo { position: absolute; inset: 0; opacity: 0; pointer-events: none; clip-path: inset(36% 0 43%);
    filter: drop-shadow(-3px 0 #ff2ee6) brightness(1.35) saturate(1.5); animation: sign-signal 5s step-end 3.1s infinite; }
  @keyframes sign-signal { 0%, 5%, to { opacity: 0; transform: none; }
    1% { opacity: .85; clip-path: inset(30% 0 40%); transform: translate(1.1%); } 2.5% { opacity: 0; }
    3.5% { opacity: .7; clip-path: inset(55% 0 20%); transform: translate(-.85%); } }
  #grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; max-width: 1100px; margin: 0 auto; }
  @media (min-width: 820px) { #grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 18px; } }
  #grid > * { aspect-ratio: 2 / 3; }
  #grid a { display: block; padding: 1px; background: rgba(255,255,255,.14); transition: background .3s, transform .12s var(--ease); }
  #grid a:hover, #grid a:focus-visible { background: rgba(255,255,255,.42); outline: none; }
  #grid a:active { transform: scale(.98); }
  #grid img { display: block; width: 100%; height: 100%; object-fit: contain; background: var(--surface); }
  #status { margin-top: 26px; font-size: 12px; letter-spacing: .1em; text-transform: uppercase; }
</style></head><body>
<div class="banner reveal"><img src="/title.png" alt="{title}"><img class="sign-echo" src="/title.png" alt="" aria-hidden="true"></div>
<div id="grid"></div>
<p id="status">Loading photos...</p>
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

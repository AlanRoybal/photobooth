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
    params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}
    if route == "POST /upload":
        return upload(event)
    if route == "GET /":
        return respond(200, GALLERY.replace("{title}", html.escape(EVENT_NAME)), "text/html")
    if route == "GET /api/photos":
        return gallery_photos(query)
    if route == "GET /{id}/{file}":
        return image(params.get("id", ""), params.get("file", ""), query)
    if route in ("GET /{id}", "GET /p/{id}"):
        return page(params.get("id", ""))
    return respond(404, {"error": "not found"})


STYLE = """
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  body { margin: 0; min-height: 100vh; background: #0b0b1a; color: #fff; text-align: center;
    font-family: -apple-system, system-ui, "Segoe UI", Roboto, sans-serif; padding: 24px 18px 40px; }
  h1 { font-size: 24px; margin: 4px 0 18px; }
  img { width: 100%; max-width: 420px; border-radius: 10px; box-shadow: 0 8px 30px rgba(0,0,0,.5); }
  .btn { display: block; width: 100%; max-width: 420px; margin: 14px auto 0; padding: 16px; border: 0; border-radius: 14px;
    font-size: 18px; font-weight: 700; color: #fff; text-decoration: none; font-family: inherit; }
  .ig { background: linear-gradient(45deg, #f9ce34, #ee2a7b, #6228d7); }
  .dl { background: rgba(255,255,255,.16); }
  .gal { background: transparent; border: 2px solid rgba(255,255,255,.35); }
  .ig:disabled { opacity: .6; }
  p { opacity: .85; line-height: 1.45; max-width: 420px; margin: 14px auto 0; }
</style>
"""

PENDING = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<meta http-equiv="refresh" content="8">""" + STYLE + """</head><body>
<h1>{title}</h1><p>Your photo is on its way. This page will refresh by itself in a few seconds.</p>
</body></html>"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>""" + STYLE + """</head><body>
<h1>{title}</h1>
<img src="{photo}" alt="Your photobooth picture">
<button id="share" class="btn ig" disabled>Share to Instagram Story</button>
<a class="btn dl" href="{download}">Download photo</a>
<a class="btn gal" href="/">View gallery</a>
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
  body { padding: 24px 12px 40px; }
  h1 { font-size: 26px; }
  #grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px;
    max-width: 1100px; margin: 0 auto; }
  #grid a { display: block; aspect-ratio: 2 / 3; border-radius: 8px; overflow: hidden; background: rgba(255,255,255,.06); }
  #grid img { width: 100%; height: 100%; max-width: none; object-fit: contain; border-radius: 0; box-shadow: none; }
  #status { margin-top: 24px; }
</style></head><body>
<h1>{title}</h1>
<div id="grid"></div>
<p id="status">Loading photos...</p>
<script>
  const grid = document.getElementById("grid");
  const status = document.getElementById("status");
  let next = 0, loading = false;
  async function more() {
    if (loading || next === null) return;
    loading = true;
    try {
      const data = await (await fetch("/api/photos?start=" + next)).json();
      data.photos.forEach((p) => {
        const a = document.createElement("a");
        a.href = "/" + p.id;
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
      status.textContent = "Couldn't load photos. Pull down to refresh.";
    }
    loading = false;
  }
  new IntersectionObserver((entries) => { if (entries[0].isIntersecting) more(); }).observe(status);
  more();
</script>
</body></html>"""

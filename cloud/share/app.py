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
FILES = ("framed.jpg", "story.jpg")

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


def get_url(photo_id, name, download=False):
    params = {"Bucket": BUCKET, "Key": key(photo_id, name)}
    if download:
        params["ResponseContentDisposition"] = f'attachment; filename="{EVENT_NAME}-{photo_id}.jpg"'.replace(" ", "-")
    return s3.generate_presigned_url("get_object", Params=params, ExpiresIn=3600)


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
        .replace("{photo}", html.escape(get_url(photo_id, "framed.jpg")))
        .replace("{download}", html.escape(get_url(photo_id, "framed.jpg", download=True)))
        .replace("{story}", json.dumps(get_url(photo_id, "story.jpg")))
        .replace("{filename}", json.dumps(f"story-{photo_id}.jpg"))
        .replace("{handle}", json.dumps(f"@{INSTAGRAM_HANDLE}" if INSTAGRAM_HANDLE else ""))
    )
    return respond(200, body, "text/html")


def handler(event, context):
    method = event["requestContext"]["http"]["method"]
    if method == "POST" and event.get("rawPath") == "/upload":
        return upload(event)
    if method == "GET" and event.get("pathParameters", {}).get("id"):
        return page(event["pathParameters"]["id"])
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
    shareBtn.hidden = true;
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

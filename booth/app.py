import base64
import io
import secrets
import threading

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import compose
import config
from camera import Camera
from printer import print_file
from uploader import Uploader

cfg = config.load()
CAPTURES = config.DATA_DIR / "captures"
PRINTS = config.DATA_DIR / "prints"
FRAMES_DIR = config.ROOT / "frames"
for d in (CAPTURES, PRINTS):
    d.mkdir(parents=True, exist_ok=True)


def clear_captures():
    for f in CAPTURES.glob("*.jpg"):
        f.unlink(missing_ok=True)


clear_captures()

ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
app = Flask(__name__, static_folder="static", static_url_path="/static")
camera = Camera(rotate_180=cfg["camera_rotate_180"], ev=cfg["camera_ev"])
uploader = Uploader(PRINTS, cfg["upload_api_url"], cfg["booth_key"])
frames = {f.id: f for f in compose.load_frames(FRAMES_DIR)}
capture_lock = threading.Lock()


def new_id(n=8):
    return "".join(secrets.choice(ID_ALPHABET) for _ in range(n))


def share_url(print_id):
    return f"{cfg['share_base_url'].rstrip('/')}/{print_id}"


def load_capture(capture_id):
    path = CAPTURES / f"{capture_id}.jpg"
    if not capture_id.isalnum() or not path.exists():
        abort(404)
    return compose.Image.open(path).convert("RGB")


def get_frame(frame_id):
    if frame_id not in frames:
        abort(404)
    return frames[frame_id]


def jpeg_response(img, quality=85):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return Response(buf.getvalue(), mimetype="image/jpeg")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/config")
def ui_config():
    keys = ("title", "countdown_seconds", "idle_timeout_seconds", "done_screen_seconds",
            "camera_arrow_x_percent", "mirror_preview")
    home = config.ROOT / "static" / "home.png"
    return jsonify({**{k: cfg[k] for k in keys}, "home_image": home.exists()})


@app.get("/stream.mjpg")
def stream():
    return Response(camera.mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/capture")
def capture():
    with capture_lock:
        img = camera.capture(mirror=cfg["mirror_photo"])
    clear_captures()
    capture_id = new_id(12)
    img.save(CAPTURES / f"{capture_id}.jpg", "JPEG", quality=95)
    return jsonify({"capture_id": capture_id, "image": f"/captures/{capture_id}.jpg"})


@app.get("/captures/<name>")
def capture_file(name):
    return send_from_directory(CAPTURES, name)


@app.get("/api/frames")
def list_frames():
    return jsonify([{"id": f.id, "name": f.name, "orientation": f.orientation,
                     "photo_w": f.photo["w"], "photo_h": f.photo["h"]} for f in frames.values()])


@app.get("/api/preview/<capture_id>/<frame_id>.jpg")
def preview(capture_id, frame_id):
    frame = get_frame(frame_id)
    img = compose.with_qr(compose.framed(load_capture(capture_id), frame), frame, share_url("preview"))
    return jpeg_response(img.resize((img.width // 2, img.height // 2), compose.Image.LANCZOS))


@app.post("/api/confirm")
def confirm():
    body = request.get_json(force=True)
    photo = load_capture(str(body.get("capture_id", "")))
    frame = get_frame(body.get("frame_id"))
    print_id = new_id()
    out = PRINTS / print_id
    out.mkdir()

    framed = compose.framed(photo, frame)
    framed.save(out / "framed.jpg", "JPEG", quality=92)
    framed.resize((framed.width * 2 // 5, framed.height * 2 // 5), compose.Image.LANCZOS).save(
        out / "thumb.jpg", "JPEG", quality=80)
    compose.story(photo, framed, frame).save(out / "story.jpg", "JPEG", quality=92)
    printed = compose.with_qr(framed, frame, share_url(print_id))
    compose.for_print(printed, cfg["print_scale"], cfg["print_gamma"]).save(out / "print.jpg", "JPEG", quality=95)
    clear_captures()

    error = None
    if cfg["print_enabled"]:
        try:
            print_file(out / "print.jpg", cfg["printer_name"], cfg["print_options"])
        except Exception as e:
            error = str(e)
            print(f"print failed: {error}")
    buf = io.BytesIO()
    printed.resize((printed.width // 2, printed.height // 2), compose.Image.LANCZOS).save(buf, "JPEG", quality=85)
    image = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    uploader.enqueue(out)
    return jsonify({"print_id": print_id, "image": image, "print_error": error})


@app.get("/prints/<print_id>/<name>")
def print_file_route(print_id, name):
    if not print_id.isalnum():
        abort(404)
    return send_from_directory(PRINTS / print_id, name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=cfg["port"], threaded=True)

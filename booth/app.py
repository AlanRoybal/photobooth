import base64
import functools
import io
import secrets
import threading

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import compose
import config
import network
from camera import Camera
from printer import job_status, print_file
from uploader import Uploader

cfg = config.load()
CAPTURES = config.DATA_DIR / "captures"
PRINTS = config.DATA_DIR / "prints"
print_jobs = {}
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
internet = network.Internet()


def new_id(n=8):
    return "".join(secrets.choice(ID_ALPHABET) for _ in range(n))


def share_url(print_id):
    return f"{cfg['share_base_url'].rstrip('/')}/{print_id}"


QR_LOGO = FRAMES_DIR / "qr-logo.png"


def add_qr(img, frame, print_id):
    # Uppercase lets the QR use compact alphanumeric mode (the share page accepts any case), so the
    # extra error correction needed for the center logo doesn't make the code denser.
    return compose.with_qr(img, frame, share_url(print_id).upper(), cfg["qr_color"],
                           QR_LOGO if QR_LOGO.exists() else None)


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
            "camera_arrow_x_percent", "mirror_preview", "screen_rotate_180",
            "screen_tilt_deg")
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
    img = add_qr(compose.framed(load_capture(capture_id), frame), frame, "preview")
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
    printed = add_qr(framed, frame, print_id)
    compose.for_print(printed, cfg["print_scale"], cfg["print_gamma"]).save(out / "print.jpg", "JPEG", quality=95)
    clear_captures()

    error = None
    job = ""
    if cfg["print_enabled"]:
        try:
            job = print_file(out / "print.jpg", cfg["printer_name"], cfg["print_options"])
            print_jobs[print_id] = job
        except Exception as e:
            error = str(e)
            print(f"print failed: {error}")
    buf = io.BytesIO()
    printed.resize((printed.width // 2, printed.height // 2), compose.Image.LANCZOS).save(buf, "JPEG", quality=85)
    image = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    uploader.enqueue(out)
    return jsonify({"print_id": print_id, "image": image, "print_error": error, "print_job": job})


@app.get("/api/print-status/<print_id>")
def print_status(print_id):
    job = print_jobs.get(print_id)
    if not job:
        return jsonify({"state": "done", "detail": ""})
    try:
        state, detail = job_status(job, cfg["printer_name"])
    except Exception as e:
        state, detail = "printing", str(e)
    if state == "done":
        print_jobs.pop(print_id, None)
    return jsonify({"state": state, "detail": detail})


@app.get("/prints/<print_id>/<name>")
def print_file_route(print_id, name):
    if not print_id.isalnum():
        abort(404)
    return send_from_directory(PRINTS / print_id, name)


def pending_uploads():
    return len(list(PRINTS.glob("*/pending")))


@app.get("/api/net")
def net_brief():
    return jsonify({"internet": internet.state, "pending": pending_uploads()})


def staff(view):
    @functools.wraps(view)
    def check(*args, **kwargs):
        pin = cfg["staff_pin"]
        if pin and not secrets.compare_digest(request.headers.get("X-Staff-Pin", ""), pin):
            return jsonify({"error": "Wrong PIN"}), 401
        return view(*args, **kwargs)
    return check


def staff_result(error):
    internet.wake.set()
    return (jsonify({"error": error}), 400) if error else jsonify({"ok": True})


@app.get("/api/staff/status")
@staff
def staff_status():
    return jsonify({**network.status(), "internet": internet.state, "portal_url": internet.portal_url,
                    "pending": pending_uploads()})


@app.get("/api/staff/printer")
@staff
def staff_printer():
    return jsonify({"found": network.printer_found()})


@app.get("/api/staff/networks")
@staff
def staff_networks():
    return jsonify(network.networks())


@app.post("/api/staff/connect")
@staff
def staff_connect():
    body = request.get_json(force=True)
    return staff_result(network.connect(str(body.get("ssid", "")), str(body.get("kind", "")),
                                        str(body.get("password", "")), str(body.get("username", ""))))


@app.post("/api/staff/use")
@staff
def staff_use():
    return staff_result(network.use(str(request.get_json(force=True).get("uuid", ""))))


@app.post("/api/staff/forget")
@staff
def staff_forget():
    return staff_result(network.forget(str(request.get_json(force=True).get("uuid", ""))))


@app.post("/api/staff/recheck")
@staff
def staff_recheck():
    return jsonify({"internet": internet.check(), "portal_url": internet.portal_url})


@app.post("/api/staff/shutdown")
@staff
def staff_shutdown():
    threading.Thread(target=network.shutdown, daemon=True).start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=cfg["port"], threaded=True)

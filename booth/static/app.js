const $ = (id) => document.getElementById(id);
const live = $("live");
const CAMERA_ASPECT = 16 / 9;
const SLIDES = { portrait: [280, 420], landscape: [480, 320] };
const state = { cfg: null, captureId: null, allFrames: [], frames: [], frameIndex: 0, orientation: "portrait",
  idleTimer: null, doneTimer: null, busy: false };

function show(name) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === name));
  document.body.classList.toggle("show-live", name === "countdown");
  clearTimeout(state.doneTimer);
  resetIdle();
}

// Fraction of the camera image (width, height) that every frame of this orientation keeps after center-cropping.
function cropFor(orientation) {
  let fw = 1, fh = 1;
  state.allFrames.filter((f) => f.orientation === orientation).forEach((f) => {
    const a = f.photo_w / f.photo_h;
    fw = Math.min(fw, a / CAMERA_ASPECT);
    fh = Math.min(fh, CAMERA_ASPECT / a);
  });
  return { fw, fh };
}

function fitBox(maxW, maxH, aspect) {
  return aspect > maxW / maxH ? [maxW, maxW / aspect] : [maxH * aspect, maxH];
}

function setOrientation(o) {
  state.orientation = o;
  state.frames = state.allFrames.filter((f) => f.orientation === o);
  document.querySelectorAll("#orient button").forEach((b) => b.classList.toggle("on", b.dataset.o === o));
  const { fw, fh } = cropFor(o);
  const [dw, dh] = fitBox(innerWidth, innerHeight, CAMERA_ASPECT);
  Object.assign($("guide").style, { width: `${dw * fw}px`, height: `${dh * fh}px` });
  const [sw, sh] = fitBox(960, 470, (CAMERA_ASPECT * fw) / fh);
  Object.assign($("shot-wrap").style, { width: `${sw}px`, height: `${sh}px` });
  const [tw, th] = SLIDES[o];
  $("frames").style.setProperty("--sw", `${tw}px`);
  $("frames").style.setProperty("--sh", `${th}px`);
}

function resetIdle() {
  clearTimeout(state.idleTimer);
  clearInterval(state.warnTimer);
  $("idle-warn").hidden = true;
  const current = document.querySelector(".screen.active").id;
  if (["start", "countdown", "printing", "done"].includes(current)) return;
  const total = state.cfg.idle_timeout_seconds;
  const warn = Math.min(10, total);
  state.idleTimer = setTimeout(() => {
    let left = warn;
    $("idle-left").textContent = left;
    $("idle-warn").hidden = false;
    state.warnTimer = setInterval(() => {
      left--;
      $("idle-left").textContent = left;
      if (left <= 0) show("start");
    }, 1000);
  }, (total - warn) * 1000);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function runCountdown() {
  if (state.busy) return;
  state.busy = true;
  live.src = "/stream.mjpg?" + Date.now();
  show("countdown");
  const count = $("count");
  for (let n = state.cfg.countdown_seconds; n > 0; n--) {
    count.textContent = n;
    count.classList.remove("tick");
    void count.offsetWidth;
    count.classList.add("tick");
    await sleep(1000);
  }
  count.textContent = "";
  const flash = $("flash");
  flash.classList.remove("on");
  void flash.offsetWidth;
  flash.classList.add("on");
  try {
    const res = await fetch("/api/capture", { method: "POST" });
    const data = await res.json();
    state.captureId = data.capture_id;
    $("shot").src = data.image;
    await $("shot").decode().catch(() => {});
    show("review");
  } catch (e) {
    console.error(e);
    show("instructions");
  } finally {
    state.busy = false;
  }
}

function renderFrames() {
  const track = $("track");
  const dots = $("dots");
  track.innerHTML = "";
  dots.innerHTML = "";
  state.frames.forEach((f) => {
    const img = document.createElement("img");
    img.src = `/api/preview/${state.captureId}/${f.id}.jpg`;
    img.alt = f.name;
    track.appendChild(img);
    dots.appendChild(document.createElement("span"));
  });
  state.frameIndex = 0;
  moveTo(0);
}

function moveTo(i) {
  const n = state.frames.length;
  state.frameIndex = (i + n) % n;
  $("track").style.transform = `translateX(${-SLIDES[state.orientation][0] * state.frameIndex}px)`;
  [...$("dots").children].forEach((d, j) => d.classList.toggle("on", j === state.frameIndex));
  resetIdle();
}

async function confirmPrint() {
  if (state.busy) return;
  state.busy = true;
  show("printing");
  try {
    const res = await fetch("/api/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capture_id: state.captureId, frame_id: state.frames[state.frameIndex].id }),
    });
    const data = await res.json();
    $("final").src = data.image;
    await $("final").decode().catch(() => {});
    if (data.print_error) {
      $("done-title").textContent = "Printer problem";
      $("done-msg").textContent = "Your photo was saved but did not print. Ask a staff member for help. You can still scan this QR code.";
    } else {
      $("done-title").textContent = "Printing now!";
      $("done-msg").textContent = "Grab your photo from the printer. Scan the QR code on it to download the picture or share it to your Instagram story.";
    }
    show("done");
    state.doneTimer = setTimeout(() => show("start"), state.cfg.done_screen_seconds * 1000);
  } catch (e) {
    console.error(e);
    show("frames");
  } finally {
    state.busy = false;
  }
}

function swipe(el, onLeft, onRight) {
  let x0 = null;
  el.addEventListener("touchstart", (e) => (x0 = e.touches[0].clientX), { passive: true });
  el.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0;
    if (dx < -40) onLeft();
    if (dx > 40) onRight();
    x0 = null;
  });
}

async function init() {
  state.cfg = await (await fetch("/api/config")).json();
  state.allFrames = await (await fetch("/api/frames")).json();
  const orientations = ["portrait", "landscape"].filter((o) => state.allFrames.some((f) => f.orientation === o));
  $("orient").hidden = orientations.length < 2;
  document.querySelectorAll("#orient button").forEach((b) =>
    b.addEventListener("click", () => { setOrientation(b.dataset.o); resetIdle(); }));
  $("title").textContent = state.cfg.title;
  $("start").classList.toggle("custom", state.cfg.home_image);
  $("arrow").style.left = `${state.cfg.camera_arrow_x_percent}%`;
  live.classList.toggle("mirror", state.cfg.mirror_preview);
  live.src = "/stream.mjpg";
  live.onerror = () => setTimeout(() => (live.src = "/stream.mjpg?" + Date.now()), 2000);

  $("start").addEventListener("click", () => { setOrientation(orientations[0]); show("instructions"); });
  $("ready").addEventListener("click", runCountdown);
  $("retake").addEventListener("click", runCountdown);
  $("next").addEventListener("click", () => { renderFrames(); show("frames"); });
  $("prev-frame").addEventListener("click", () => moveTo(state.frameIndex - 1));
  $("next-frame").addEventListener("click", () => moveTo(state.frameIndex + 1));
  swipe($("track-window"), () => moveTo(state.frameIndex + 1), () => moveTo(state.frameIndex - 1));
  $("frames-back").addEventListener("click", () => show("review"));
  $("confirm").addEventListener("click", confirmPrint);
  $("finish").addEventListener("click", () => show("start"));
  document.querySelectorAll(".cancel").forEach((b) => b.addEventListener("click", () => show("start")));
  document.addEventListener("pointerdown", resetIdle);
  document.addEventListener("contextmenu", (e) => e.preventDefault());
}

init();

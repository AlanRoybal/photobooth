const $ = (id) => document.getElementById(id);
const live = $("live");
const state = { cfg: null, captureId: null, frames: [], frameIndex: 0, idleTimer: null, doneTimer: null, busy: false };

function show(name) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === name));
  document.body.classList.toggle("show-live", name === "countdown");
  clearTimeout(state.doneTimer);
  resetIdle();
}

function resetIdle() {
  clearTimeout(state.idleTimer);
  const current = document.querySelector(".screen.active").id;
  if (["start", "countdown", "printing", "done"].includes(current)) return;
  state.idleTimer = setTimeout(() => show("start"), state.cfg.idle_timeout_seconds * 1000);
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
  $("track").style.transform = `translateX(${-280 * state.frameIndex}px)`;
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
  state.frames = await (await fetch("/api/frames")).json();
  $("title").textContent = state.cfg.title;
  $("arrow").style.left = `${state.cfg.camera_arrow_x_percent}%`;
  live.classList.toggle("mirror", state.cfg.mirror_preview);
  live.src = "/stream.mjpg";
  live.onerror = () => setTimeout(() => (live.src = "/stream.mjpg?" + Date.now()), 2000);

  $("start").addEventListener("click", () => show("instructions"));
  $("ready").addEventListener("click", runCountdown);
  $("retake").addEventListener("click", runCountdown);
  $("next").addEventListener("click", () => { renderFrames(); show("frames"); });
  $("prev-frame").addEventListener("click", () => moveTo(state.frameIndex - 1));
  $("next-frame").addEventListener("click", () => moveTo(state.frameIndex + 1));
  swipe($("track-window"), () => moveTo(state.frameIndex + 1), () => moveTo(state.frameIndex - 1));
  $("frames-back").addEventListener("click", () => show("review"));
  $("confirm").addEventListener("click", confirmPrint);
  $("finish").addEventListener("click", () => show("start"));
  document.addEventListener("pointerdown", resetIdle);
  document.addEventListener("contextmenu", (e) => e.preventDefault());
}

init();

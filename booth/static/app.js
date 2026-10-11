const $ = (id) => document.getElementById(id);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const live = $("live");
const CAMERA_ASPECT = 16 / 9;
const CARD_W = { portrait: 186, landscape: 360 };
const state = { cfg: null, captureId: null, allFrames: [], frames: [], frameIndex: 0, orientation: "portrait",
  landscapeK: 0, cardS: [1, 1], cardO: [1, 1], pos: 0, idleTimer: null, warnTimer: null, doneTimer: null,
  lock: false, screen: "start", run: 0, orientations: ["portrait"] };

// Motion helpers (same formulas as the Figma "00 Read me" page).
const cl = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const prog = (t, a, b) => cl((t - a) / (b - a));
const lerp = (a, b, k) => a + (b - a) * k;
const eoc = (x) => 1 - Math.pow(1 - x, 3);
const eic = (x) => x * x * x;
const eio = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
function spring(t, start, dur, damp = 0.8) {
  const el = t - start;
  if (el <= 0) return 0;
  if (el >= dur) return 1;
  const om = 5 / (damp * dur), od = om * Math.sqrt(1 - damp * damp), k = (damp * om) / od;
  const pos = (x) => 1 - Math.exp(-damp * om * x) * (Math.cos(od * x) + k * Math.sin(od * x));
  const p = el / dur;
  return pos(el) + (1 - pos(dur)) * (p * p * (3 - 2 * p));
}
const press = (t) => 1 - 0.04 * eoc(prog(t, 0, 0.12));
const UNITS = { x: "px", y: "px", dx: "px", dy: "px", r: "deg" };
function set(el, vars) {
  if (!el) return;
  for (const k in vars) el.style.setProperty("--" + k, typeof vars[k] === "number" ? vars[k] + (UNITS[k] || "") : vars[k]);
}
const rise = (r, o = 1) => ({ dy: 90 * (1 - r), s: 0.9 + 0.1 * r, o });
function mix(a, b, k) {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const [x, y] = [p(a), p(b)];
  return "rgb(" + x.map((v, i) => Math.round(lerp(v, y[i], k))).join(",") + ")";
}

// Runs fn(t) every frame for dur seconds. A newer play()/loop() cancels older ones.
function play(dur, fn) {
  const id = ++state.run;
  return new Promise((resolve) => {
    const t0 = performance.now();
    const step = (now) => {
      if (id !== state.run) return resolve(false);
      const t = Math.min((now - t0) / 1000, dur);
      fn(t);
      if (t >= dur) return resolve(true);
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}
function loop(fn) {
  const id = ++state.run;
  const t0 = performance.now();
  const step = (now) => {
    if (id !== state.run) return;
    fn((now - t0) / 1000);
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const STEP = { instructions: 0, review: 1, frames: 2, printing: 3, done: 3 };
function clearVars(root) {
  [root, ...$$(".a, .step, .art", root)].forEach((el) =>
    ["--o", "--s", "--dy", "--dx", "--r", "--sy", "--bga", "--t2"].forEach((p) => el.style.removeProperty(p)));
}
function screenOn(name, on = true) {
  $(name).classList.toggle("on", on);
  if (on) clearVars($(name));
}
function setChrome(name) {
  const cur = STEP[name];
  $("chrome").classList.toggle("on", cur !== undefined);
  clearVars($("chrome"));
  $$("#progress i").forEach((d, i) => (d.className = i < cur ? "done" : i === cur ? "cur" : ""));
  $("progress").classList.remove("complete");
  $$(".cancel").forEach((b) => (b.style.display = ["instructions", "review", "frames"].includes(name) ? "" : "none"));
}
function show(name) {
  $$(".screen").forEach((s) => s.classList.toggle("on", s.id === name));
  clearVars($(name));
  setChrome(name);
  state.screen = name;
  document.body.classList.toggle("show-live", name === "countdown");
  clearTimeout(state.doneTimer);
  resetIdle();
}
function barIn(e) { set($("progress"), { s: 0.6 + 0.4 * e, o: Math.min(2 * e, 1) }); }

// Crop of the camera image (fraction of width, height) kept by every frame of this orientation.
function cropFor(orientation) {
  let fw = 1, fh = 1;
  state.allFrames.filter((f) => f.orientation === orientation).forEach((f) => {
    const a = f.photo_w / f.photo_h;
    fw = Math.min(fw, a / CAMERA_ASPECT);
    fh = Math.min(fh, CAMERA_ASPECT / a);
  });
  return { fw, fh };
}
const fitBox = (maxW, maxH, aspect) => (aspect > maxW / maxH ? [maxW, maxW / aspect] : [maxH * aspect, maxH]);
function windowBox() {
  const { fw, fh } = cropFor(state.orientation);
  const [dw, dh] = fitBox(1024, 600, CAMERA_ASPECT);
  return { w: dw * fw, h: dh * fh, y: 300 };
}
function restBox() {
  const { w, h } = windowBox();
  return state.orientation === "portrait" ? { w: (279 * w) / h, h: 279, y: 326 } : { w: 390, h: (390 * h) / w, y: 326 };
}
function setOrientation(o) {
  state.orientation = o;
  state.frames = state.allFrames.filter((f) => f.orientation === o);
  const { fw, fh } = cropFor(o);
  const [dw, dh] = fitBox(innerWidth, innerHeight, CAMERA_ASPECT);
  Object.assign($("guide").style, { width: `${dw * fw}px`, height: `${dh * fh}px` });
}

// Photo card on Review: k = 0 at the crop window (live view), 1 at rest.
function photoCard(k, o = 1) {
  const a = windowBox(), b = restBox(), border = lerp(0, 10, k);
  const el = $("shot-wrap");
  Object.assign(el.style, { width: `${lerp(a.w, b.w, k) + 2 * border}px`, height: `${lerp(a.h, b.h, k) + 2 * border}px`,
    padding: `${border}px` });
  set(el, { y: lerp(a.y, b.y, k), r: lerp(0, -2, k), o });
}

function paintOrient() {
  $$("#orient .opt").forEach((b, i) => {
    const k = i ? state.landscapeK : 1 - state.landscapeK;
    set(b, { s: (0.94 + 0.06 * k) * state.cardS[i], r: (i ? 4 : -4) * (1 - k), o: (0.7 + 0.3 * k) * state.cardO[i], k,
      fill: mix("#121019", "#2A0E52", k), icon: mix("#5A5470", "#B48CFF", k), label: mix("#DBC4FF", "#F4F2FF", k) });
  });
}

// A: Start entrance, then B: idle loop.
function startPaint(t) {
  set($("home-art"), { o: eoc(prog(t, 0, 0.5)) });
  set($("panel"), { o: prog(t, 0.15, 0.45), s: lerp(0.9, 1, spring(t, 0.15, 0.7, 0.6)),
    t2: eoc(prog(t, 0.3, 0.75)) });
  $$(".step").forEach((el, i) => {
    const s = 0.6 + 0.08 * i;
    set(el, { o: prog(t, s, s + 0.2), dy: 16 * (1 - spring(t, s, 0.6, 0.6)) });
  });
  set($("go"), rise(spring(t, 1.4, 0.6, 0.65), prog(t, 1.4, 1.8)));
}
async function enterStart() {
  show("start");
  state.lock = true;
  await play(2, startPaint);
  state.lock = false;
  loop((t) => {
    set($("panel"), { dy: 4 * Math.sin((2 * Math.PI * t) / 6.5) });
    set($("go"), { s: 1 + 0.025 * Math.sin((2 * Math.PI * t) / 1.625) });
  });
}
// O: any screen -> Start.
async function goStart() {
  if (state.screen === "start") return;
  clearInterval(state.warnTimer);
  clearTimeout(state.idleTimer);
  clearTimeout(state.doneTimer);
  $("idle-warn").hidden = true;
  const old = $(state.screen);
  state.lock = true;
  $("chrome").classList.remove("on");
  document.body.classList.remove("show-live");
  screenOn("start");
  startPaint(0);
  await play(0.2, (t) => set(old, { o: 1 - eoc(prog(t, 0, 0.2)) }));
  state.lock = false;
  enterStart();
}

// Shared "dex page stretch" (C and I): press, stretch + fade out, then the incoming screen settles.
async function stretchTo(from, btn, fade, to, enter, dur = 1.52) {
  state.lock = true;
  const fromArt = $(from).querySelector(".art");
  let swapped = false;
  await play(dur, (t) => {
    const t1 = t - 0.12;
    if (t < 0.37) {
      set($(btn), { s: press(t) });
      set(fromArt, { sy: 1 + 0.06 * eic(prog(t1, 0, 0.25)) });
      fade.forEach((el) => set(el, { o: 1 - prog(t1, 0, 0.15) }));
      return;
    }
    if (!swapped) { swapped = true; show(to); state.lock = true; }
    const u = t - 0.37;
    set($(to).querySelector(".art"), { sy: 1 + 0.06 * Math.pow(1 - prog(u, 0, 0.4), 3) });
    barIn(spring(u, 0, 0.7, 0.8));
    set($$(".cancel")[0], { o: prog(u, 0, 0.2) });
    const r = eoc(prog(u, 0.4, 0.85));
    set($(to).querySelector(".cap"), { dy: 36 * (1 - r), o: r });
    enter(u);
  });
  state.lock = false;
}

function toInstructions() {
  setOrientation(state.orientations[0]);
  state.landscapeK = state.orientation === "landscape" ? 1 : 0;
  return stretchTo("start", "go", [$("panel"), $("go")], "instructions", (u) => {
    set($("arrow"), { dy: -70 * (1 - spring(u, 0.05, 0.8, 0.55)), o: prog(u, 0.05, 0.2) });
    state.cardS = [0.15, 0.21].map((a) => lerp(0.4, 1, spring(u, a, 0.6, 0.6)));
    state.cardO = [0.15, 0.21].map((a) => prog(u, a, a + 0.15));
    paintOrient();
    set($("ready"), rise(spring(u, 0.55, 0.6, 0.65), prog(u, 0.55, 0.8)));
  });
}

// D: layout toggle.
async function toggleOrient(o) {
  if (state.lock || o === state.orientation) return;
  setOrientation(o);
  const from = state.landscapeK, to = o === "landscape" ? 1 : 0;
  await play(0.5, (t) => { state.landscapeK = lerp(from, to, spring(t, 0, 0.5, 0.68)); paintOrient(); });
}

// Countdown pieces (E, F, H).
function countIn(u, chipA, ringA, numA) {
  set($("chip"), { o: prog(u, chipA, chipA + 0.2), dy: -20 * (1 - spring(u, chipA, 0.6, 0.6)) });
  set($("ring"), { s: lerp(0.6, 1, spring(u, ringA, 0.6, 0.65)), o: prog(u, ringA, ringA + 0.15) });
  set($("count"), { s: lerp(1.6, 1, spring(u, numA, 0.6, 0.7)), o: prog(u, numA, numA + 0.15), r: -12 * (1 - spring(u, numA, 0.7, 0.55)) });
}
function tick(t, R) {
  set($("count-old"), { s: 1 - 0.35 * eic(prog(t, 0, 0.18)), o: 1 - prog(t, 0, 0.18) });
  set($("count"), { s: lerp(1.6, 1, spring(t, 0.08, 0.6, 0.7)), o: prog(t, 0.08, 0.2), r: R * (1 - spring(t, 0.08, 0.7, 0.55)) });
}
function startLive() {
  live.src = "/stream.mjpg?" + Date.now();
  screenOn("countdown");
  document.body.classList.add("show-live");
  set($("count-old"), { o: 0 });
  $("count").textContent = state.cfg.countdown_seconds;
}

async function countdownThenCapture() {
  for (let n = state.cfg.countdown_seconds - 1; n > 0; n--) {
    $("count-old").textContent = $("count").textContent;
    $("count").textContent = n;
    await play(1, (t) => tick(t, n % 2 ? 12 : -12));
  }
  // G: shutter flash while capturing, then the photo drops onto Review.
  $("count-old").textContent = $("count").textContent;
  $("count").textContent = "";
  let data = null;
  const req = fetch("/api/capture", { method: "POST" }).then((r) => r.json()).then((d) => (data = d)).catch((e) => console.error(e));
  await play(0.5, (t) => {
    set($("count-old"), { s: 1 - 0.35 * eic(prog(t, 0, 0.18)), o: 1 - prog(t, 0, 0.18) });
    set($("flash"), { o: t < 0.06 ? eoc(prog(t, 0, 0.06)) : 1 - eoc(prog(t, 0.06, 0.5)) });
  });
  set($("flash"), { o: 0 });
  await req;
  if (!data) { state.lock = false; show("instructions"); paintOrient(); return; }
  state.captureId = data.capture_id;
  $("shot").src = data.image;
  await $("shot").decode().catch(() => {});
  show("review");
  state.lock = true;
  screenOn("countdown");
  document.body.classList.add("show-live");
  set($("count-old"), { o: 0 }); set($("chip"), { o: 0 }); set($("ring"), { o: 0 });
  await play(1.2, (t) => {
    const u = t + 0.1;
    set($("review"), { bga: eoc(prog(u, 0.1, 0.35)) });
    photoCard(spring(u, 0.1, 0.85, 0.72));
    barIn(spring(u, 0.3, 0.7, 0.8));
    set($$(".cancel")[0], { o: prog(u, 0.3, 0.5) });
    const r = eoc(prog(u, 0.4, 0.85));
    set($("review").querySelector(".cap"), { dy: 36 * (1 - r), o: r });
    const b = rise(spring(u, 0.6, 0.6, 0.65), prog(u, 0.6, 0.85));
    set($("retake"), b); set($("next"), b);
  });
  screenOn("countdown", false);
  document.body.classList.remove("show-live");
  state.lock = false;
}

// E: Ready -> Countdown.
async function readyToCountdown() {
  if (state.lock) return;
  state.lock = true;
  startLive();
  clearTimeout(state.idleTimer);
  const fade = [$("instructions"), $("chrome")];
  await play(1, (t) => {
    const u = t - 0.12;
    set($("ready"), { s: press(t) });
    fade.forEach((el) => set(el, { o: 1 - eoc(prog(u, 0, 0.2)) }));
    set($("guide"), { o: eoc(prog(u, 0.05, 0.35)) });
    countIn(u, 0.2, 0.2, 0.3);
  });
  show("countdown");
  state.lock = true;
  await countdownThenCapture();
}

// H: Retake.
async function retake() {
  if (state.lock) return;
  state.lock = true;
  startLive();
  clearTimeout(state.idleTimer);
  $("review").style.zIndex = 1;
  const fade = [$("review").querySelector(".cap"), $("retake"), $("next"), $("chrome")];
  await play(1.12, (t) => {
    const u = t - 0.12;
    set($("retake"), { s: press(t) });
    photoCard(1 - eio(prog(u, 0, 0.35)), 1 - prog(u, 0.25, 0.4));
    fade.forEach((el) => set(el, { o: 1 - prog(u, 0, 0.15) }));
    set($("review"), { bga: 1 - prog(u, 0.15, 0.4) });
    countIn(u, 0.3, 0.35, 0.4);
  });
  $("review").style.zIndex = "";
  show("countdown");
  state.lock = true;
  await countdownThenCapture();
}

// Frame carousel (I, J, K).
function layoutCards(pos, fan, exit = 0) {
  const imgs = $$("#track img"), n = imgs.length, fw = CARD_W[state.orientation], pitch = fw + 76;
  imgs.forEach((img, i) => {
    let rel = i - pos;
    if (n > 2) rel = ((((rel + n / 2) % n) + n) % n) - n / 2;
    const re = rel * fan, a = Math.min(Math.abs(re), 1), focused = Math.abs(rel) < 0.5;
    let cx = 512 + re * pitch, r = -6 * cl(re, -1, 1);
    let o = Math.abs(re) <= 1 ? 1 - 0.5 * a : Math.max(0, 0.5 * (2 - Math.abs(re)));
    if (exit) {
      if (focused) o = 0;
      else { cx += Math.sign(rel) * 80 * exit; r *= 1 + exit; o *= 1 - exit; }
    }
    img.style.width = `${fw * (1 - 0.3 * a)}px`;
    img.style.zIndex = 10 - Math.round(Math.abs(rel) * 2);
    img.style.transform = `translate(${cx}px, 326px) translate(-50%, -50%) rotate(${r}deg)`;
    img.style.opacity = o;
  });
  set($("prev-frame"), { x: 512 - pitch / 2 }); set($("next-frame"), { x: 512 + pitch / 2 });
}
function renderFrames() {
  const track = $("track");
  track.innerHTML = "";
  state.frames.forEach((f) => {
    const img = document.createElement("img");
    img.src = `/api/preview/${state.captureId}/${f.id}.jpg`;
    img.alt = f.name;
    track.appendChild(img);
  });
  state.frameIndex = 0;
  state.pos = 0;
}
function toFrames() {
  if (state.lock) return;
  renderFrames();
  return stretchTo("review", "next", [$("review").querySelector(".cap"), $("retake"), $("next"), $("chrome")], "frames", (u) => {
    layoutCards(0, spring(u, 0.05, 0.75, 0.7));
    const ao = prog(u, 0.45, 0.7);
    set($("prev-frame"), { o: ao }); set($("next-frame"), { o: ao });
    const b = rise(spring(u, 0.55, 0.6, 0.65), prog(u, 0.55, 0.8));
    set($("frames-back"), b); set($("confirm"), b);
  });
}
// J: scrub to the next/previous frame.
async function moveTo(dir) {
  if (state.lock || state.frames.length < 2) return;
  resetIdle();
  const from = state.pos, to = from + dir, btn = dir > 0 ? $("next-frame") : $("prev-frame");
  state.frameIndex = (((state.frameIndex + dir) % state.frames.length) + state.frames.length) % state.frames.length;
  state.pos = to;
  await play(0.7, (t) => {
    set(btn, { s: t < 0.12 ? press(t) : 0.96 + 0.04 * eoc(prog(t, 0.12, 0.24)) });
    layoutCards(lerp(from, to, spring(t, 0.12, 0.55, 0.82)), 1);
  });
}
function backToReview() {
  if (state.lock) return;
  show("review");
  photoCard(1);
}

// K: Confirm -> Printing, L: printing loop, M: Printing -> Done.
function paperAt(cy, w, r, clipY) {
  const slot = $("slot"), paper = $("paper");
  slot.style.height = `${clipY}px`;
  paper.style.width = `${w}px`;
  set(paper, { x: 512, y: cy, r, o: 1 });
}
async function confirmPrint() {
  if (state.lock) return;
  state.lock = true;
  clearTimeout(state.idleTimer);
  const frame = state.frames[state.frameIndex];
  const focused = $$("#track img")[state.frameIndex];
  $("paper").src = focused.src;
  let data = null;
  const req = fetch("/api/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ capture_id: state.captureId, frame_id: frame.id }),
  }).then((r) => r.json()).then((d) => (data = d)).catch((e) => console.error(e));

  const land = state.orientation === "landscape";
  const pw = land ? 180 : 120, ph = land ? 120 : 180, fw = CARD_W[state.orientation];
  screenOn("printing");
  set($("printing"), { bga: 0 });
  const fade = [$("frames").querySelector(".cap"), $("frames-back"), $("confirm"), $("prev-frame"), $("next-frame"), $$(".cancel")[0]];
  let slotY = 378;
  await play(1.3, (t) => {
    const u = t - 0.12;
    set($("confirm"), { s: press(t) });
    layoutCards(state.pos, 1, eoc(prog(u, 0, 0.3)));
    fade.forEach((el) => set(el, { o: 1 - prog(u, 0, 0.15) }));
    const pdy = 260 * (1 - spring(u, 0.05, 0.6, 0.62));
    set($("printer"), { dy: pdy, o: prog(u, 0.05, 0.2) });
    slotY = 378 + pdy;
    if (u < 0.6) {
      const k = eio(prog(u, 0.05, 0.55));
      paperAt(lerp(326, 288, k), lerp(fw, pw, k), lerp(0, -3, k), 600);
    } else {
      const d = eic(prog(u, 0.6, 0.95));
      paperAt(slotY - 90 + 117 * d, pw, lerp(-3, 0, d), slotY);
    }
    const r = eoc(prog(u, 0.6, 1.05));
    set($("printing").querySelector(".cap"), { dy: 36 * (1 - r), o: r });
    $$("#pdots i").forEach((d) => set(d, { o: prog(u, 0.9, 1.1) }));
  });
  $("frames").classList.remove("on");
  set($("printing"), { bga: 1 });
  state.screen = "printing";
  setChrome("printing");

  let done = false;
  req.then(() => (done = true));
  const loopPaint = (t) => {
    const rp = 0.35 + 0.2 * Math.sin((2 * Math.PI * t) / 2.4);
    const dy = 1.5 * Math.sin((2 * Math.PI * t) / 0.6);
    set($("printer"), { dy, o: 1 });
    paperAt(378 + dy + ph / 2 - ph * rp, pw, 0, 378 + dy);
    $$("#pdots i").forEach((d, i) => set(d, { o: 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(2 * Math.PI * (t / 1.2 - 0.15 * i))) }));
  };
  let t0 = 0;
  while (!done || t0 < 2.4) {
    const start = t0;
    await play(0.1, (t) => loopPaint(start + t));
    t0 += 0.1;
  }
  if (!data) { state.lock = false; show("frames"); layoutCards(state.pos, 1); return; }

  $("final").src = data.image;
  await $("final").decode().catch(() => {});
  if (data.print_error) {
    $("done-title").textContent = "Printer problem";
    $("done-msg").textContent = "Your photo was saved but did not print. Ask a staff member for help.";
  } else {
    $("done-title").textContent = "Grab your print!";
    $("done-msg").textContent = "Scan its QR code to download it or share it to your story.";
  }
  screenOn("done");
  $("check").style.display = data.print_error ? "none" : "";
  set($("done"), { bga: 0 });
  const doneW = land ? 270 : 180;
  const loopEnd = t0;
  await play(1.45, (t) => {
    const co = 1 - prog(t, 0, 0.15);
    set($("printing").querySelector(".cap"), { o: co });
    $$("#pdots i").forEach((d) => set(d, { o: co }));
    const pdy = 260 * eic(prog(t, 0.4, 0.75));
    set($("printer"), { dy: pdy, o: 1 - prog(t, 0.55, 0.75) });
    if (t < 0.35) {
      const rp = lerp(0.35 + 0.2 * Math.sin((2 * Math.PI * loopEnd) / 2.4), 1, eoc(prog(t, 0, 0.35)));
      paperAt(378 + ph / 2 - ph * rp, pw, 0, 378);
      set($("final-wrap"), { o: 0 });
    } else {
      set($("paper"), { o: 0 });
      const k = spring(t, 0.35, 0.8, 0.7);
      $("final-wrap").style.width = `${lerp(pw, doneW, k)}px`;
      set($("final-wrap"), { y: lerp(288, 326, k), r: lerp(0, 6, k), o: 1 });
    }
    set($("check"), { s: spring(t, 0.9, 0.5, 0.5), r: -25 * (1 - spring(t, 0.9, 0.6, 0.55)) });
    const r = eoc(prog(t, 0.5, 0.95));
    set($("done").querySelector(".cap"), { dy: 36 * (1 - r), o: r });
    $("progress").classList.toggle("complete", t >= 0.6 && !data.print_error);
    set($("finish"), rise(spring(t, 0.8, 0.6, 0.65), prog(t, 0.8, 1.05)));
  });
  $("printing").classList.remove("on");
  set($("done"), { bga: 1 });
  state.screen = "done";
  state.lock = false;
  state.doneTimer = setTimeout(goStart, state.cfg.done_screen_seconds * 1000);
}

// N: idle warning.
function resetIdle() {
  clearTimeout(state.idleTimer);
  clearInterval(state.warnTimer);
  const warnEl = $("idle-warn");
  if (!warnEl.hidden) {
    const o0 = 1;
    const fadeOut = (t) => set(warnEl, { o: o0 * (1 - eoc(prog(t, 0, 0.15))) });
    let s0 = null;
    const f = (now) => { s0 = s0 || now; const t = (now - s0) / 1000; fadeOut(t); if (t < 0.15) requestAnimationFrame(f); else warnEl.hidden = true; };
    requestAnimationFrame(f);
  }
  if (!["instructions", "review", "frames"].includes(state.screen)) return;
  const total = state.cfg.idle_timeout_seconds;
  const warn = Math.min(10, total);
  state.idleTimer = setTimeout(() => {
    let left = warn;
    const paintNum = () => {
      $("idle-left").textContent = left;
      $("idle-num").textContent = left;
      $("idle-arc").style.strokeDashoffset = 364.4 * (1 - left / warn);
    };
    paintNum();
    warnEl.hidden = false;
    let s0 = null;
    const f = (now) => {
      s0 = s0 || now;
      const t = (now - s0) / 1000, r = eoc(prog(t, 0.1, 0.45));
      set(warnEl, { o: eoc(prog(t, 0, 0.25)) });
      $$("h2, p", warnEl).forEach((el) => set(el, { dy: 36 * (1 - r), o: r }));
      set($("idle-ring"), { s: lerp(0.6, 1, spring(t, 0.05, 0.6, 0.65)) });
      if (t < 0.6 && !warnEl.hidden) requestAnimationFrame(f);
    };
    requestAnimationFrame(f);
    state.warnTimer = setInterval(() => {
      left--;
      paintNum();
      if (left <= 0) { clearInterval(state.warnTimer); goStart(); }
    }, 1000);
  }, (total - warn) * 1000);
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

function fit() { $("stage").style.setProperty("--fit", Math.min(innerWidth / 1024, innerHeight / 600)); }

async function init() {
  fit();
  addEventListener("resize", fit);
  state.cfg = await (await fetch("/api/config")).json();
  state.allFrames = await (await fetch("/api/frames")).json();
  state.orientations = ["portrait", "landscape"].filter((o) => state.allFrames.some((f) => f.orientation === o));
  $("orient").hidden = state.orientations.length < 2;
  $("home-art").classList.toggle("custom", !!state.cfg.home_image);
  set($("arrow"), { x: (1024 * state.cfg.camera_arrow_x_percent) / 100 });
  live.classList.toggle("mirror", state.cfg.mirror_preview);
  live.onerror = () => setTimeout(() => (live.src = "/stream.mjpg?" + Date.now()), 2000);

  $("start").addEventListener("click", () => { if (!state.lock) toInstructions(); });
  $$("#orient .opt").forEach((b) => b.addEventListener("click", () => { toggleOrient(b.dataset.o); resetIdle(); }));
  $("ready").addEventListener("click", readyToCountdown);
  $("retake").addEventListener("click", retake);
  $("next").addEventListener("click", toFrames);
  $("prev-frame").addEventListener("click", () => moveTo(-1));
  $("next-frame").addEventListener("click", () => moveTo(1));
  swipe($("track"), () => moveTo(1), () => moveTo(-1));
  $("frames-back").addEventListener("click", backToReview);
  $("confirm").addEventListener("click", confirmPrint);
  $("finish").addEventListener("click", () => { if (!state.lock) goStart(); });
  $$(".cancel").forEach((b) => b.addEventListener("click", () => { if (!state.lock) goStart(); }));
  document.addEventListener("pointerdown", () => { if (state.screen !== "start") resetIdle(); });
  document.addEventListener("contextmenu", (e) => e.preventDefault());
  enterStart();
}

init();

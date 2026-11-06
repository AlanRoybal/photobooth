// Staff menu: long-press the top-left corner of the start screen to manage Wi-Fi, check the printer, or shut down.
(() => {
  const S = { pin: "", nets: [], page: 0, net: null, f: { user: "", pass: "" }, focus: "pass", shift: false, sym: false,
    reveal: false, busy: false, poll: null, longFired: false, holdTimer: null, offTimer: null };
  const PER_PAGE = 5;
  const INTERNET = { online: "Online", portal: "Needs sign-in page", offline: "No internet" };
  const KIND = { open: "Open", owe: "Open", psk: "Password", sae: "Password", enterprise: "NetID login" };
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

  async function api(path, body) {
    const r = await fetch(path, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json", "X-Staff-Pin": S.pin },
      body: body ? JSON.stringify(body) : undefined });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(d.error || `Error ${r.status}`); e.status = r.status; throw e; }
    return d;
  }
  const view = (name) => $$("#staff > .sv").forEach((v) => (v.hidden = v.id !== name));

  // Opening, PIN and closing.
  async function open() {
    if (state.screen !== "start" || state.lock) return;
    S.pin = "";
    $("staff").hidden = false;
    try { await api("/api/staff/status"); main(); } catch (e) { if (e.status === 401) pinView(); else main(); }
  }
  function close() {
    clearInterval(S.poll);
    $("staff-frame").src = "about:blank";
    $("staff").hidden = true;
    S.pin = "";
  }
  function pinView(msg = "Enter the staff PIN") {
    S.entry = "";
    $("pin-msg").textContent = msg;
    paintPin();
    view("staff-pin");
  }
  function paintPin() { $("pin-dots").textContent = S.entry ? "•".repeat(S.entry.length) : " "; }
  async function pinKey(k) {
    if (k === "⌫") S.entry = S.entry.slice(0, -1);
    else if (k === "OK") {
      S.pin = S.entry;
      try { await api("/api/staff/status"); return main(); } catch (e) { return pinView(e.status === 401 ? "Wrong PIN, try again" : e.message); }
    } else if (S.entry.length < 12) S.entry += k;
    paintPin();
  }

  // Main view: status + network list.
  function main(note = "") {
    view("staff-main");
    $("st-note").textContent = note;
    refreshStatus();
    clearInterval(S.poll);
    S.poll = setInterval(refreshStatus, 4000);
    checkPrinter();
    scan();
  }
  async function refreshStatus() {
    try {
      const d = await api("/api/staff/status");
      $("st-wifi").textContent = d.ssid ? `${d.ssid}${d.signal ? ` (${d.signal}%)` : ""}` : "Not connected";
      $("st-internet").textContent = INTERNET[d.internet] || d.internet;
      $("st-internet").className = d.internet === "online" ? "good" : "bad";
      $("st-pending").textContent = d.pending;
      $("st-pending").className = d.pending && d.internet !== "online" ? "bad" : "";
      $("st-ip").textContent = d.ip || "-";
      $("st-mac").textContent = d.mac || "-";
      $("st-portal").hidden = d.internet !== "portal";
      S.portalUrl = d.portal_url;
    } catch (e) { if (e.status === 401) pinView(); }
  }
  async function checkPrinter() {
    $("st-printer").textContent = "Looking...";
    $("st-printer").className = "";
    try {
      const d = await api("/api/staff/printer");
      $("st-printer").textContent = d.found ? "Found on this network" : "Not found on this network";
      $("st-printer").className = d.found ? "good" : "bad";
    } catch { $("st-printer").textContent = "-"; }
  }
  async function scan() {
    $("net-list").innerHTML = "";
    $("net-list").appendChild(el("li", "empty", "Scanning for Wi-Fi..."));
    $("net-page").textContent = "";
    try { S.nets = await api("/api/staff/networks"); } catch (e) { S.nets = []; $("net-list").firstChild.textContent = e.message; return; }
    S.page = 0;
    paintNets();
  }
  function paintNets() {
    const list = $("net-list"), pages = Math.max(1, Math.ceil(S.nets.length / PER_PAGE));
    S.page = Math.min(S.page, pages - 1);
    list.innerHTML = "";
    if (!S.nets.length) list.appendChild(el("li", "empty", "No Wi-Fi networks found"));
    S.nets.slice(S.page * PER_PAGE, (S.page + 1) * PER_PAGE).forEach((n) => {
      const li = el("li", n.active ? "on" : "");
      const name = el("span", "ssid", n.ssid);
      const tags = el("span", "tags", [n.active ? "Connected" : n.saved.length ? "Saved" : "", n.in_range ? KIND[n.kind] : "Not in range"]
        .filter(Boolean).join(" · "));
      const bars = el("span", "bars");
      for (let i = 1; i <= 4; i++) bars.appendChild(el("i", n.signal >= i * 22 ? "lit" : ""));
      li.append(name, tags, bars);
      li.addEventListener("click", () => joinView(n));
      list.appendChild(li);
    });
    $("net-page").textContent = pages > 1 ? `${S.page + 1} / ${pages}` : "";
    $("net-up").disabled = S.page === 0;
    $("net-down").disabled = S.page >= pages - 1;
  }

  // Join view: saved network actions or password entry with the on-screen keyboard.
  function joinView(n) {
    S.net = n;
    S.f = { user: "", pass: "" };
    S.reveal = false;
    S.shift = false;
    S.sym = false;
    $("join-title").textContent = n.ssid;
    $("join-msg").textContent = "";
    $("join-msg").className = "";
    const needs = n.kind === "enterprise" ? ["user", "pass"] : ["psk", "sae"].includes(n.kind) ? ["pass"] : [];
    S.needs = n.in_range ? needs : [];
    $("join-saved").hidden = !n.saved.length;
    $("join-hint").textContent = !n.in_range ? "This saved network isn't in range right now."
      : n.saved.length ? "Saved on the booth. Connect with the saved password, or type a new one below."
      : n.kind === "enterprise" ? "Sign in with a NetID (or other school username) and password."
      : needs.length ? "Type the Wi-Fi password." : "Open network, no password needed.";
    S.focus = S.needs[0] || "";
    $("join-connect").hidden = !n.in_range || (!S.needs.length && n.saved.length > 0);
    $("join-connect").textContent = n.saved.length ? "Save & connect" : "Connect";
    $("join-use").hidden = !n.in_range || !n.saved.length;
    paintJoin();
    view("staff-join");
  }
  function paintJoin() {
    ["user", "pass"].forEach((f) => {
      const box = $(`field-${f}`);
      box.hidden = !S.needs.includes(f);
      box.classList.toggle("focus", S.focus === f);
      const v = S.f[f];
      box.querySelector("b").textContent = f === "pass" && !S.reveal ? "•".repeat(v.length) : v;
    });
    $("join-reveal").hidden = !S.needs.includes("pass");
    $("join-reveal").textContent = S.reveal ? "Hide" : "Show";
    $("osk").hidden = !S.needs.length;
    paintKeys();
  }
  const LAYOUT = {
    abc: ["1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm"],
    sym: ["1234567890", "!@#$%^&*()", "-_=+[]{}\\|", ";:'\",.<>/?", "`~"],
  };
  function paintKeys() {
    const osk = $("osk");
    osk.innerHTML = "";
    const rowsOf = S.sym ? LAYOUT.sym : LAYOUT.abc;
    rowsOf.forEach((chars, i) => {
      const row = el("div", "row");
      if (!S.sym && i === 3) row.appendChild(key("⇧", "wide" + (S.shift ? " lit" : "")));
      [...chars].forEach((c) => row.appendChild(key(S.shift && !S.sym ? c.toUpperCase() : c)));
      if (i === rowsOf.length - 1) row.appendChild(key("⌫", "wide"));
      osk.appendChild(row);
    });
    const last = el("div", "row");
    last.append(key(S.sym ? "abc" : "#+=", "wide"), key("space", "space"), key(".", ""), key("@", ""));
    osk.appendChild(last);
  }
  function key(label, cls = "") {
    const b = el("button", "key " + cls, label);
    b.addEventListener("pointerdown", (e) => { e.preventDefault(); type(label); });
    return b;
  }
  function type(k) {
    if (!S.focus) return;
    if (k === "⇧") S.shift = !S.shift;
    else if (k === "#+=" || k === "abc") S.sym = !S.sym;
    else if (k === "⌫") S.f[S.focus] = S.f[S.focus].slice(0, -1);
    else { S.f[S.focus] += k === "space" ? " " : k; if (S.shift) S.shift = false; }
    paintJoin();
  }
  async function act(label, fn) {
    if (S.busy) return;
    S.busy = true;
    $$("#staff-join .actions button").forEach((b) => (b.disabled = true));
    $("join-msg").className = "";
    $("join-msg").textContent = label;
    try { await fn(); } catch (e) {
      if (e.status === 401) { S.busy = false; return pinView(); }
      $("join-msg").className = "bad";
      $("join-msg").textContent = e.message;
    }
    $$("#staff-join .actions button").forEach((b) => (b.disabled = false));
    S.busy = false;
  }
  const connect = () => act("Connecting... this can take up to a minute.", async () => {
    const n = S.net;
    await api("/api/staff/connect", { ssid: n.ssid, kind: n.kind, password: S.f.pass, username: S.f.user });
    main(`Connected to ${n.ssid}.`);
  });
  const useSaved = () => act("Connecting... this can take up to a minute.", async () => {
    let err = null;
    for (const uuid of S.net.saved) {
      try { await api("/api/staff/use", { uuid }); return main(`Connected to ${S.net.ssid}.`); } catch (e) { if (e.status === 401) throw e; err = e; }
    }
    throw err;
  });
  const forget = () => act("Forgetting...", async () => {
    for (const uuid of S.net.saved) await api("/api/staff/forget", { uuid });
    main(`Forgot ${S.net.ssid}.`);
  });

  // Captive portal: the venue's sign-in page inside the booth UI.
  function portal() {
    clearInterval(S.poll);
    $("staff-frame").src = S.portalUrl || "http://neverssl.com/";
    view("staff-portal");
  }
  async function portalDone() {
    $("staff-frame").src = "about:blank";
    await api("/api/staff/recheck", {}).catch(() => {});
    main();
  }

  function shutdown() {
    const b = $("st-off");
    if (!b.classList.contains("armed")) {
      b.classList.add("armed");
      b.textContent = "Tap again to shut down";
      S.offTimer = setTimeout(() => { b.classList.remove("armed"); b.textContent = "Shut down"; }, 4000);
      return;
    }
    clearTimeout(S.offTimer);
    api("/api/staff/shutdown", {}).then(() => {
      clearInterval(S.poll);
      view("staff-off");
    }).catch((e) => { $("st-note").textContent = e.message; });
  }

  // Status chip on the start screen when photos can't upload.
  async function chip() {
    try {
      const d = await (await fetch("/api/net")).json();
      const c = $("net-chip");
      c.hidden = d.internet === "online";
      c.textContent = d.pending ? `No internet · ${d.pending} photo${d.pending === 1 ? "" : "s"} waiting to upload` : "No internet";
    } catch {}
  }

  function wire() {
    const corner = $("staff-corner");
    const cancelHold = () => clearTimeout(S.holdTimer);
    corner.addEventListener("pointerdown", () => {
      S.longFired = false;
      cancelHold();
      S.holdTimer = setTimeout(() => { S.longFired = true; open(); }, 2000);
    });
    ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => corner.addEventListener(ev, cancelHold));
    corner.addEventListener("click", (e) => { if (S.longFired) { e.stopPropagation(); S.longFired = false; } });

    const pad = $("pinpad");
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "OK"].forEach((k) => {
      const b = el("button", "key" + (k === "OK" ? " go" : ""), k);
      b.addEventListener("click", () => pinKey(k));
      pad.appendChild(b);
    });
    $("pin-cancel").addEventListener("click", close);
    $("staff-close").addEventListener("click", close);
    $("net-rescan").addEventListener("click", scan);
    $("net-up").addEventListener("click", () => { S.page--; paintNets(); });
    $("net-down").addEventListener("click", () => { S.page++; paintNets(); });
    $("st-printer-check").addEventListener("click", checkPrinter);
    $("st-portal").addEventListener("click", portal);
    $("st-off").addEventListener("click", shutdown);
    $("join-back").addEventListener("click", () => { if (!S.busy) main(); });
    $("join-connect").addEventListener("click", connect);
    $("join-use").addEventListener("click", useSaved);
    $("join-forget").addEventListener("click", forget);
    $("join-reveal").addEventListener("click", () => { S.reveal = !S.reveal; paintJoin(); });
    ["user", "pass"].forEach((f) => $(`field-${f}`).addEventListener("click", () => { S.focus = f; paintJoin(); }));
    $("portal-done").addEventListener("click", portalDone);
    chip();
    setInterval(chip, 10000);
  }
  wire();
})();

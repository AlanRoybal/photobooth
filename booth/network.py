"""Wi-Fi control for the staff menu, through NetworkManager (nmcli) and keyfiles."""
import subprocess
import threading
import time
import uuid
from pathlib import Path

import requests

IFACE = "wlan0"
CONN_DIR = "/etc/NetworkManager/system-connections"
CHECK_URL = "http://connectivitycheck.gstatic.com/generate_204"
NEW_PRIORITY = 20


def run(*args, input=None, timeout=20):
    return subprocess.run(["sudo", "-n", *args], input=input, capture_output=True, text=True, timeout=timeout)


def nmcli(*args, timeout=20):
    return run("nmcli", *args, timeout=timeout)


def fields(line):
    """Split one line of `nmcli -t` output, which escapes ':' and '\\' with a backslash."""
    out, cur, i = [], "", 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if c == ":":
            out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    out.append(cur)
    return out


def rows(result):
    return [fields(line) for line in result.stdout.splitlines() if line]


def kind(security):
    s = security.upper()
    if "802.1X" in s:
        return "enterprise"
    if s in ("", "--"):
        return "open"
    if "OWE" in s and "WPA" not in s:
        return "owe"
    if "WPA3" in s and "WPA2" not in s and "WPA1" not in s:
        return "sae"
    return "psk"


class Internet:
    """Checks for internet in the background: 'online', 'portal' (sign-in page) or 'offline'."""

    def __init__(self, every=20):
        self.state, self.portal_url, self.wake = "offline", "", threading.Event()
        self.every = every
        threading.Thread(target=self._loop, daemon=True).start()

    def check(self):
        try:
            r = requests.get(CHECK_URL, allow_redirects=False, timeout=5)
            if r.status_code == 204:
                self.state, self.portal_url = "online", ""
            else:
                loc = r.headers.get("Location", "")
                self.state, self.portal_url = "portal", loc if loc.startswith("http") else ""
        except requests.RequestException:
            self.state, self.portal_url = "offline", ""
        return self.state

    def _loop(self):
        while True:
            self.check()
            self.wake.wait(self.every)
            self.wake.clear()


def mac():
    try:
        return Path(f"/sys/class/net/{IFACE}/address").read_text().strip()
    except OSError:
        return ""


def status():
    active = next((r for r in rows(nmcli("-t", "-f", "ACTIVE,SSID,SIGNAL", "device", "wifi", "list", "--rescan", "no"))
                   if len(r) >= 3 and r[0] == "yes"), None)
    ip = nmcli("-g", "IP4.ADDRESS", "device", "show", IFACE).stdout.split("|")[0].strip().split("/")[0]
    return {"ssid": active[1] if active else "", "signal": int(active[2] or 0) if active else 0,
            "ip": ip, "mac": mac()}


def saved():
    out = []
    for name, uid, typ, filename in (r[:4] for r in rows(nmcli("-t", "-f", "NAME,UUID,TYPE,FILENAME", "connection", "show"))
                                     if len(r) >= 4):
        if typ != "802-11-wireless":
            continue
        ssid = nmcli("-g", "802-11-wireless.ssid", "connection", "show", "uuid", uid).stdout.strip() or name
        out.append({"uuid": uid, "name": name, "ssid": ssid, "filename": filename})
    return out


def networks():
    seen = {}
    for r in rows(nmcli("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes", timeout=30)):
        if len(r) < 4 or not r[1]:
            continue
        signal = int(r[2] or 0)
        if r[1] not in seen or signal > seen[r[1]]["signal"]:
            seen[r[1]] = {"ssid": r[1], "signal": signal, "kind": kind(r[3]), "active": r[0] == "*", "in_range": True}
        elif r[0] == "*":
            seen[r[1]]["active"] = True
    profiles = saved()
    for p in profiles:
        if p["ssid"] not in seen:
            seen[p["ssid"]] = {"ssid": p["ssid"], "signal": 0, "kind": "", "active": False, "in_range": False}
    for n in seen.values():
        n["saved"] = [p["uuid"] for p in profiles if p["ssid"] == n["ssid"]]
    return sorted(seen.values(), key=lambda n: (not n["active"], not n["in_range"], -n["signal"], n["ssid"].lower()))


def esc(value):
    v = value.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return "\\s" + v[1:] if v.startswith(" ") else v


def keyfile(uid, ssid, kind_, password="", username=""):
    lines = ["[connection]", f"id={esc(ssid)}", f"uuid={uid}", "type=wifi", f"interface-name={IFACE}",
             "autoconnect=true", f"autoconnect-priority={NEW_PRIORITY}", "",
             "[wifi]", "mode=infrastructure", f"ssid={esc(ssid)}", ""]
    if kind_ in ("psk", "sae"):
        lines += ["[wifi-security]", f"key-mgmt={'sae' if kind_ == 'sae' else 'wpa-psk'}", f"psk={esc(password)}", ""]
    elif kind_ == "owe":
        lines += ["[wifi-security]", "key-mgmt=owe", ""]
    elif kind_ == "enterprise":
        lines += ["[wifi-security]", "key-mgmt=wpa-eap", "",
                  "[802-1x]", "eap=peap;", f"identity={esc(username)}", f"password={esc(password)}",
                  "phase2-auth=mschapv2", ""]
    lines += ["[ipv4]", "method=auto", "", "[ipv6]", "method=auto", ""]
    return "\n".join(lines)


def connect(ssid, kind_, password="", username=""):
    """Saves a new profile for ssid (replacing ones this menu made before) and joins it. Returns an error or None."""
    if kind_ not in ("open", "owe", "psk", "sae", "enterprise"):
        return "Unknown Wi-Fi security type"
    if kind_ in ("psk", "sae") and len(password) < 8:
        return "Wi-Fi passwords are at least 8 characters"
    for p in saved():
        if p["ssid"] == ssid and Path(p["filename"]).name.startswith("booth-"):
            nmcli("connection", "delete", "uuid", p["uuid"])
    uid = str(uuid.uuid4())
    path = f"{CONN_DIR}/booth-{uid}.nmconnection"
    steps = [run("tee", path, input=keyfile(uid, ssid, kind_, password, username)),
             run("chmod", "600", path), nmcli("connection", "load", path)]
    failed = next((s for s in steps if s.returncode != 0), None)
    if failed:
        run("rm", "-f", path)
        return failed.stderr.strip() or "Could not save the network"
    return use(uid, forget_on_fail=True)


def use(uid, forget_on_fail=False):
    r = nmcli("--wait", "45", "connection", "up", "uuid", uid, timeout=60)
    if r.returncode == 0:
        return None
    if forget_on_fail:
        nmcli("connection", "delete", "uuid", uid)
    msg = r.stderr.strip()
    if "Secrets were required" in msg or "802-1x" in msg.lower():
        return "Wrong password or username, or the network refused the login"
    return msg.splitlines()[-1].removeprefix("Error: ") if msg else "Could not connect"


def forget(uid):
    r = nmcli("connection", "delete", "uuid", uid)
    return None if r.returncode == 0 else (r.stderr.strip() or "Could not forget the network")


def printer_found(timeout=10):
    """True if a SELPHY is advertising itself on the current network."""
    try:
        out = subprocess.run(["driverless"], capture_output=True, text=True, timeout=timeout).stdout
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    except OSError:
        return False
    return "selphy" in out.lower()


def shutdown():
    time.sleep(1)
    run("systemctl", "poweroff")

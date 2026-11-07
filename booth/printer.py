import re
import subprocess


def print_file(path, printer, options):
    """Send a file to CUPS and return the job id (e.g. "SELPHY-12")."""
    status = subprocess.run(["lpstat", "-p", printer], capture_output=True, text=True, timeout=10).stdout
    if "disabled" in status:
        print(f"printer queue was stopped, re-enabling: {status.strip()}")
        subprocess.run(["/usr/sbin/cupsenable", printer], capture_output=True, timeout=10)
    result = subprocess.run(
        ["lp", "-d", printer, *options, str(path)], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "lp failed")
    m = re.search(r"request id is (\S+)", result.stdout)
    return m.group(1) if m else ""


def job_status(job_id, printer):
    """("printing" | "done" | "error", detail). CUPS keeps an IPP job open until the printer finishes it."""
    queued = subprocess.run(
        ["lpstat", "-W", "not-completed", "-o", printer], capture_output=True, text=True, timeout=10
    ).stdout
    if not any(line.split()[:1] == [job_id] for line in queued.splitlines()):
        return "done", ""
    info = subprocess.run(["lpstat", "-p", printer, "-l"], capture_output=True, text=True, timeout=10).stdout
    if "disabled" in info:
        return "error", "printer queue stopped"
    alerts = re.findall(r"[\w-]+-error\b", info)
    return ("error", ", ".join(alerts)) if alerts else ("printing", "")

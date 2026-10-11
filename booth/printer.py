import subprocess


def print_file(path, printer, options):
    status = subprocess.run(["lpstat", "-p", printer], capture_output=True, text=True, timeout=10).stdout
    if "disabled" in status:
        print(f"printer queue was stopped, re-enabling: {status.strip()}")
        subprocess.run(["/usr/sbin/cupsenable", printer], capture_output=True, timeout=10)
    result = subprocess.run(
        ["lp", "-d", printer, *options, str(path)], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "lp failed")
    return result.stdout.strip()

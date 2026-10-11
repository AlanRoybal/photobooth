import subprocess


def print_file(path, printer, options):
    result = subprocess.run(
        ["lp", "-d", printer, *options, str(path)], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "lp failed")
    return result.stdout.strip()

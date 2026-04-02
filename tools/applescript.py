"""AppleScript runner — shared helper for all macOS automation."""

import subprocess


def run(script: str) -> str:
    """Execute an AppleScript and return stdout."""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip()


def run_ok(script: str) -> bool:
    """Execute an AppleScript and return True if it succeeded."""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.returncode == 0

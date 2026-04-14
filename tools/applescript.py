"""AppleScript runner — shared helper for all macOS automation."""

import subprocess

# osascript error -1743 means the app lacks Accessibility / Automation permission.
# Surface this as a clear message rather than silently returning empty output.
_AX_DENIED_CODES = {"-1743", "-25211"}
_AX_DENIED_MSG = (
    "macOS Accessibility permission denied. "
    "Go to System Settings → Privacy & Security → Accessibility "
    "and enable Clawspan (or Terminal/your launcher)."
)


def run(script: str) -> str:
    """Execute an AppleScript and return stdout.

    Returns a human-readable error string when Accessibility is denied
    instead of silently returning empty output.
    """
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        stderr = r.stderr.strip()
        if any(code in stderr for code in _AX_DENIED_CODES):
            return _AX_DENIED_MSG
        if stderr:
            return f"AppleScript error: {stderr[:200]}"
    return r.stdout.strip()


def run_ok(script: str) -> bool:
    """Execute an AppleScript and return True if it succeeded."""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.returncode == 0

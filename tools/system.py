"""macOS system control — volume, brightness, sleep, lock, screenshot."""

import os
import subprocess

from tools import applescript


def control(action: str, value: int = -1) -> str:
    """Execute a system control action."""
    print(f"[Tool] System: {action} {value}")

    if action == "volume_up":
        applescript.run("set volume output volume (output volume of (get volume settings) + 10)")
        return "Volume up."
    elif action == "volume_down":
        applescript.run("set volume output volume (output volume of (get volume settings) - 10)")
        return "Volume down."
    elif action == "volume_set" and value >= 0:
        applescript.run(f"set volume output volume {value}")
        return f"Volume set to {value}%."
    elif action == "mute":
        applescript.run("set volume with output muted")
        return "Muted."
    elif action == "sleep":
        subprocess.run(["pmset", "sleepnow"])
        return "Sleeping."
    elif action == "lock":
        subprocess.run(["pmset", "displaysleepnow"])
        return "Screen locked."
    elif action == "screenshot":
        path = os.path.expanduser("~/Desktop/screenshot.png")
        subprocess.run(["screencapture", "-x", path])
        return "Screenshot saved to Desktop."
    elif action == "brightness_up":
        return "Use keyboard brightness keys."

    return f"Unknown action: {action}"

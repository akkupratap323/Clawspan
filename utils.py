"""
Clawspan Utilities
"""

import subprocess
import sys


def print_banner():
    from datetime import datetime
    now = datetime.now().strftime("%H:%M · %d %b %Y").upper()
    print(f"""
  C · L · A · W · S · P · A · N
  ─────────────────────────────
  SYSTEMS ONLINE  ·  {now}
""")


def play_sound(sound_type: str):
    """Play system sounds as audio feedback."""
    sounds = {
        "activated": "Ping",
        "deactivated": "Basso",
        "error": "Sosumi",
        "success": "Glass",
    }
    sound = sounds.get(sound_type, "Ping")
    sound_path = f"/System/Library/Sounds/{sound}.aiff"
    try:
        subprocess.Popen(
            ["afplay", sound_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        # Not on macOS or sound file missing — silently skip
        pass

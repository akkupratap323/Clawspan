"""
Clawspan Utilities
"""

import os


def print_banner():
    from datetime import datetime
    now = datetime.now().strftime("%H:%M · %d %b %Y").upper()
    print(f"""
  J · A · R · V · I · S
  ─────────────────────────
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
    os.system(f"afplay /System/Library/Sounds/{sound}.aiff 2>/dev/null &")

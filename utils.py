"""
Clawspan Utilities
"""

import os


def print_banner():
    print("""
+====================================================+
|                                                      |
|        J . A . R . V . I . S                         |
|   Just A Rather Very Intelligent System              |
|                                                      |
|   STT  : Deepgram Nova-2 (real-time)                 |
|   TTS  : Cartesia Sonic                              |
|   Wake : Double Clap                                 |
|   Exit : Say "goodbye" or Ctrl+C                     |
|                                                      |
|   Brain: DeepSeek V3 (2-3s, no limit)                |
|   Claude Code CLI for deep reasoning                 |
|                                                      |
+====================================================+
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

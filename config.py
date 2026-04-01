"""
JARVIS Configuration
Add your API keys here or set as environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── API Keys ─────────────────────────────────────────────────────────────────

DEEPGRAM_API_KEY    = os.getenv("DEEPGRAM_API_KEY", "")
CARTESIA_API_KEY    = os.getenv("CARTESIA_API_KEY", "")
DEEPSEEK_API_KEY    = os.getenv("DEEPSEEK_API_KEY", "")
GOOGLE_CLIENT_ID    = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_TOKEN_FILE   = os.path.expanduser("~/.jarvis_google_token.json")
GITHUB_TOKEN        = os.getenv("GITHUB_TOKEN", "")
TAVILY_API_KEY      = os.getenv("TAVILY_API_KEY", "")
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")

# ─── DeepSeek (Primary Brain — reliable tool calling, no daily limit) ────────

DEEPSEEK_MODEL    = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# ─── Cartesia Voice ──────────────────────────────────────────────────────────

CARTESIA_VOICE_ID = os.getenv(
    "CARTESIA_VOICE_ID",
    "694f9389-aac1-45b6-b726-9d9369183238"  # British JARVIS-like voice
)

# ─── Audio Settings ──────────────────────────────────────────────────────────

CLAP_THRESHOLD     = 500
CLAPS_REQUIRED     = 2
CLAP_TIMEOUT       = 1.5
SILENCE_TIMEOUT    = 2.5

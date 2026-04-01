"""ResponseFilter — centralized response post-processing.

Used by BOTH voice and text pipelines:
  - Error messages → friendly alternatives
  - Long results → LLM summarization
  - Duplicate responses → suppressed
  - Markdown/code/URLs stripped for voice
  - Emotional tone matching
"""

from __future__ import annotations

import re
import time
from typing import Any

# Error detection patterns
_ERROR_PREFIXES = (
    "OCR error:", "Vision error:", "Error:", "Failed:", "Could not find",
    "Unknown tool:", "Tool error:", "Authentication error:", "Connection refused",
    "Connection error:", "Timeout", "404", "500", "503",
)

# Friendly error alternatives
_ERROR_REPLACEMENTS = {
    "Could not find": "Sorry sir, I couldn't find that on screen.",
    "OCR error:": "I had trouble reading the screen.",
    "Vision error:": "I couldn't see that clearly.",
    "Failed:": "That didn't work, sir.",
    "Unknown tool:": "I don't have that capability yet.",
    "Tool error:": "Something went wrong with that command.",
    "Authentication error:": "I need to re-authenticate with Google.",
    "Connection refused": "I can't reach that service right now.",
    "Connection error:": "Network issue, sir.",
    "Timeout": "That took too long, sir.",
    "404": "That page isn't available.",
    "500": "The server had an issue.",
    "503": "That service is temporarily unavailable.",
}

# Track recent responses for dedup
_last_response: str = ""
_last_response_time: float = 0
_DEDUP_WINDOW = 10  # seconds


def _is_error(text: str) -> bool:
    return any(text.startswith(p) for p in _ERROR_PREFIXES)


def _friendly_error(text: str) -> str:
    for prefix, replacement in _ERROR_REPLACEMENTS.items():
        if prefix in text:
            return replacement
    return "That didn't work, sir. Something went wrong."


def _strip_voice_unsafe(text: str) -> str:
    """Remove markdown, code blocks, URLs from spoken output."""
    # Code blocks
    text = re.sub(r'```[\s\S]*?```', 'a code snippet', text)
    # Inline code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Markdown links
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Bold/italic
    text = re.sub(r'[*_]{1,3}([^*_]+)[*_]{1,3}', r'\1', text)
    # URLs
    text = re.sub(r'https?://\S+', 'a link', text)
    # Lists
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
    # Headers
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    return text.strip()


def _summarize_for_voice(text: str, max_chars: int = 150) -> str:
    """Simple truncation + cleanup for voice (no extra LLM call)."""
    if len(text) <= max_chars:
        return text
    # Truncate at sentence boundary
    truncated = text[:max_chars]
    last_period = truncated.rfind('.')
    if last_period > max_chars // 2:
        return truncated[:last_period + 1]
    return truncated.rstrip() + '...'


def _is_duplicate(text: str) -> bool:
    """Check if this response is a duplicate within the dedup window."""
    global _last_response, _last_response_time
    now = time.time()
    if text.strip().lower() == _last_response.strip().lower():
        if now - _last_response_time < _DEDUP_WINDOW:
            return True
    return False


def _record_response(text: str) -> None:
    global _last_response, _last_response_time
    _last_response = text.strip().lower()
    _last_response_time = time.time()


def _match_tone(user_input: str, response: str) -> str:
    """Adjust tone based on user input style."""
    lower = user_input.lower().strip()

    # User seems frustrated — short, repeated, commands
    frustration_signals = ("hurry", "fast", "now", "do it", "come on", "why isn't", "not working", "fix")
    if any(s in lower for s in frustration_signals):
        if not response.lower().startswith(("on it", "right away", "doing", "done")):
            response = "On it right away. " + response

    # User is casual / friendly
    friendly_signals = ("hey", "hi", "hello", "good morning", "good evening", "how are", "what's up")
    if any(s in lower for s in friendly_signals):
        if not any(w in response.lower() for w in ("hey", "hi", "good", "morning", "evening", "afternoon")):
            response = response  # Don't double-greet

    return response


class ResponseFilter:
    """Centralized response post-processing."""

    def __init__(self, mode: str = "voice") -> None:
        """
        mode: "voice" (strips formatting, truncates) or "text" (preserves formatting)
        """
        self._mode = mode

    def process(
        self,
        raw_response: str,
        user_input: str = "",
    ) -> str:
        """Process a raw response through all filters."""
        if not raw_response:
            return "Done, sir."

        text = raw_response

        # 1. Error detection → friendly
        if _is_error(text):
            text = _friendly_error(text)

        # 2. Dedup
        if _is_duplicate(text):
            return ""  # Signal to skip speaking

        # 3. Voice-specific cleanup
        if self._mode == "voice":
            text = _strip_voice_unsafe(text)
            text = _summarize_for_voice(text)

        # 4. Tone matching
        if user_input:
            text = _match_tone(user_input, text)

        # 5. Record for dedup
        if text:
            _record_response(text)

        return text


# Module-level convenience (used by voice pipeline)
_voice_filter = ResponseFilter(mode="voice")
_text_filter = ResponseFilter(mode="text")


def filter_voice(response: str, user_input: str = "") -> str:
    return _voice_filter.process(response, user_input)


def filter_text(response: str, user_input: str = "") -> str:
    return _text_filter.process(response, user_input)

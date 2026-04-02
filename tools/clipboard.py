"""Clipboard operations — pbcopy / pbpaste."""

import subprocess


def read() -> str:
    """Read current clipboard contents."""
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    content = result.stdout
    if not content:
        return "Clipboard is empty."
    if len(content) > 2000:
        content = content[:2000] + "...(truncated)"
    return content


def write(text: str) -> str:
    """Write text to clipboard."""
    subprocess.run(["pbcopy"], input=text, text=True)
    return f"Copied to clipboard ({len(text)} chars)."

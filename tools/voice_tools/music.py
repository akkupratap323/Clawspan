"""Music voice tools: Apple Music + YouTube Music."""

from __future__ import annotations

from tools.music import apple_music, yt_music


def exec_music_control(action: str, query: str = "", volume: int = -1, **_kw) -> str:
    """Apple Music control (play, pause, next, previous, volume, shuffle, current, like)."""
    return apple_music(action, query, volume)


def exec_yt_music(query: str, **_kw) -> str:
    """Play a song or artist on YouTube Music."""
    return yt_music(query)

"""Apple Music and YouTube Music control."""

import subprocess
import time
import urllib.parse

from tools import applescript


_SCRIPTS = {
    "play":     'tell application "Music" to play',
    "pause":    'tell application "Music" to pause',
    "next":     'tell application "Music" to next track',
    "previous": 'tell application "Music" to previous track',
    "shuffle":  'tell application "Music" to set shuffle enabled to true',
    "like":     'tell application "Music" to set loved of current track to true',
}


def apple_music(action: str, query: str = "", volume: int = -1) -> str:
    """Control Apple Music."""
    print(f"[Tool] Music: {action}")

    if action == "volume" and volume >= 0:
        script = f'tell application "Music" to set sound volume to {volume}'
    elif action == "current":
        script = '''tell application "Music"
            set tName to name of current track
            set tArtist to artist of current track
            return tArtist & " - " & tName
        end tell'''
    elif action == "play" and query:
        script = f'''tell application "Music"
            set results to (every playlist whose name contains "{query}")
            if results is not {{}} then
                play item 1 of results
            else
                play
            end if
        end tell'''
    else:
        script = _SCRIPTS.get(action, "")

    if not script:
        return f"Unknown music action: {action}"

    out = applescript.run(script)
    return out if out else f"Music {action} done."


def yt_music(query: str) -> str:
    """Play a song on YouTube Music in Chrome."""
    print(f"[Tool] YT Music: {query}")
    from tools.chrome import control as chrome
    encoded = urllib.parse.quote(query)
    url = f"https://music.youtube.com/search?q={encoded}"

    chrome("open_url", url)
    time.sleep(3)

    # Try clicking Play via accessibility
    from tools.mouse import find_and_click
    result = find_and_click("Play", min_y=130, exact=True)
    if "clicked" in result.lower() or "found" in result.lower():
        return f"Playing {query} on YouTube Music."
    return f"Opened YouTube Music search for {query}. Click Play to start."

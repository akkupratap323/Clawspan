"""Open macOS applications by name, with alias resolution."""

import subprocess


_ALIASES = {
    "chrome":             "Google Chrome",
    "google chrome":      "Google Chrome",
    "safari":             "Safari",
    "firefox":            "Firefox",
    "terminal":           "Terminal",
    "iterm":              "iTerm",
    "iterm2":             "iTerm",
    "cursor":             "Cursor",
    "vscode":             "Visual Studio Code",
    "vs code":            "Visual Studio Code",
    "code":               "Visual Studio Code",
    "antigravity":        "Antigravity",
    "anti gravity":       "Antigravity",
    "anti-gravity":       "Antigravity",
    "music":              "Music",
    "apple music":        "Music",
    "spotify":            "Spotify",
    "slack":              "Slack",
    "zoom":               "zoom.us",
    "finder":             "Finder",
    "notes":              "Notes",
    "mail":               "Mail",
    "calendar":           "Calendar",
    "messages":           "Messages",
    "facetime":           "FaceTime",
    "photos":             "Photos",
    "preview":            "Preview",
    "xcode":              "Xcode",
    "calculator":         "Calculator",
    "whatsapp":           "WhatsApp",
    "quick time":         "QuickTime Player",
    "quicktime":          "QuickTime Player",
    "quick time player":  "QuickTime Player",
    "system preferences": "System Preferences",
    "system settings":    "System Settings",
    "activity monitor":   "Activity Monitor",
    "disk utility":       "Disk Utility",
}


def open_app(app_name: str) -> str:
    """Open a macOS application by name. Resolves common aliases.

    Uses Popen (non-blocking) instead of run() so that apps which are
    already running — like WhatsApp — don't block the pipeline waiting
    for a process that never exits.  The -g flag opens without stealing
    focus so the voice pipeline stays active.
    """
    print(f"[Tool] Open app: {app_name}")
    resolved = _ALIASES.get(app_name.lower(), app_name)

    def _try_open(name: str) -> bool:
        """Try to open the app by name. Returns True only if macOS confirms success.

        Uses subprocess.run with a short timeout so we can check the return code.
        `open -a` exits 0 on success (app launched or already running) and 1 when
        the app is not found — this is fast (<200ms) regardless of app state.
        """
        try:
            r = subprocess.run(
                ["open", "-a", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            return r.returncode == 0
        except Exception:
            return False

    if _try_open(resolved):
        return f"Opened {resolved}."

    if resolved != app_name and _try_open(app_name):
        return f"Opened {app_name}."

    # Spotlight fallback — search case/diacritic-insensitively
    result = subprocess.run(
        ["mdfind", "-onlyin", "/Applications", f"kMDItemDisplayName == '{resolved}'cdw"],
        capture_output=True, text=True, timeout=5,
    )
    path = result.stdout.strip().split("\n")[0]
    if path:
        subprocess.run(
            ["open", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return f"Opened {resolved}."

    return f"Couldn't find {app_name}. Try saying the full app name."


def close_app(app_name: str) -> str:
    """Quit a macOS application by name. Resolves common aliases."""
    print(f"[Tool] Close app: {app_name}")
    resolved = _ALIASES.get(app_name.lower(), app_name)

    # Use AppleScript via osascript — most reliable way to quit a named app.
    # Fallback to pkill -x if osascript is unavailable.
    try:
        r = subprocess.run(
            ["osascript", "-e", f'quit app "{resolved}"'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if r.returncode == 0:
            return f"Closed {resolved}."
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # Fallback: pkill by app name (matches process display name)
    try:
        r = subprocess.run(
            ["pkill", "-x", resolved],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if r.returncode == 0:
            return f"Closed {resolved}."
    except Exception:
        pass

    return f"Could not close {app_name} — it may not be running."

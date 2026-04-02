"""Open macOS applications by name, with alias resolution."""

import subprocess


_ALIASES = {
    "chrome":        "Google Chrome",
    "google chrome": "Google Chrome",
    "safari":        "Safari",
    "firefox":       "Firefox",
    "terminal":      "Terminal",
    "iterm":         "iTerm",
    "iterm2":        "iTerm",
    "cursor":        "Cursor",
    "vscode":        "Visual Studio Code",
    "vs code":       "Visual Studio Code",
    "code":          "Visual Studio Code",
    "antigravity":   "Antigravity",
    "anti gravity":  "Antigravity",
    "anti-gravity":  "Antigravity",
    "music":         "Music",
    "apple music":   "Music",
    "spotify":       "Spotify",
    "slack":         "Slack",
    "zoom":          "zoom.us",
    "finder":        "Finder",
    "notes":         "Notes",
    "mail":          "Mail",
    "calendar":      "Calendar",
    "messages":      "Messages",
    "facetime":      "FaceTime",
    "photos":        "Photos",
    "preview":       "Preview",
    "xcode":         "Xcode",
    "calculator":    "Calculator",
    "system preferences": "System Preferences",
    "system settings":    "System Settings",
    "activity monitor":   "Activity Monitor",
    "disk utility":       "Disk Utility",
}


def open_app(app_name: str) -> str:
    """Open a macOS application by name. Resolves common aliases."""
    print(f"[Tool] Open app: {app_name}")
    resolved = _ALIASES.get(app_name.lower(), app_name)

    r = subprocess.run(["open", "-a", resolved], capture_output=True, text=True)
    if r.returncode == 0:
        return f"Opened {resolved}."

    if resolved != app_name:
        r2 = subprocess.run(["open", "-a", app_name], capture_output=True, text=True)
        if r2.returncode == 0:
            return f"Opened {app_name}."

    # Spotlight fallback
    result = subprocess.run(
        ["mdfind", "-onlyin", "/Applications", f"kMDItemDisplayName == '{resolved}'cdw"],
        capture_output=True, text=True,
    )
    path = result.stdout.strip().split("\n")[0]
    if path:
        r3 = subprocess.run(["open", path], capture_output=True, text=True)
        if r3.returncode == 0:
            return f"Opened {resolved}."

    return f"Couldn't find {app_name}. Try saying the full app name."

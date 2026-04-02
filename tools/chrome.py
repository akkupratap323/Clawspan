"""Chrome browser control via AppleScript."""

from tools import applescript


_SCRIPTS = {
    "open_url": lambda v: f'tell application "Google Chrome" to set URL of active tab of front window to "{v}"',
    "new_tab": lambda v: 'tell application "Google Chrome" to make new tab at end of tabs of front window',
    "close_tab": lambda v: 'tell application "Google Chrome" to close active tab of front window',
    "reload": lambda v: 'tell application "Google Chrome" to reload active tab of front window',
    "back": lambda v: 'tell application "Google Chrome" to go back active tab of front window',
    "get_url": lambda v: 'tell application "Google Chrome" to get URL of active tab of front window',
    "get_title": lambda v: 'tell application "Google Chrome" to get title of active tab of front window',
}

_ACTION_ONLY = {"new_tab", "close_tab", "reload", "back", "open_url"}


def control(action: str, value: str = "") -> str:
    """Execute a Chrome action. Returns result text."""
    print(f"[Tool] Chrome: {action} {value}")
    script_fn = _SCRIPTS.get(action)
    if not script_fn:
        return f"Unknown Chrome action: {action}"

    result = applescript.run(script_fn(value))

    if action in _ACTION_ONLY:
        return "Done."
    return result or "Done."

"""Finder and file/folder operations."""

import os
import subprocess


def _spotlight_find(name: str) -> str | None:
    """Use Spotlight (mdfind) to locate a file or folder by name anywhere on disk.

    Returns the best matching path or None if nothing found.
    Tries exact display-name match first, then partial match.
    """
    for query in [
        f"kMDItemDisplayName == '{name}'cdw",
        f"kMDItemFSName == '*{name}*'cdw",
    ]:
        result = subprocess.run(
            ["mdfind", query],
            capture_output=True, text=True, timeout=6,
        )
        paths = [p for p in result.stdout.strip().splitlines() if p]
        # Prefer paths in home dir, then shortest path
        home = os.path.expanduser("~")
        home_paths = [p for p in paths if p.startswith(home)]
        candidates = home_paths or paths
        if candidates:
            return sorted(candidates, key=len)[0]
    return None


def _resolve_path(name: str) -> tuple[str, bool]:
    """Resolve a name to a real path. Returns (path, found_via_spotlight).

    Tries in order:
    1. Literal path / ~ expansion
    2. Common locations (Desktop, Documents, Downloads, home)
    3. Spotlight full-disk search
    """
    # 1. Literal
    expanded = os.path.expanduser(name)
    if os.path.exists(expanded):
        return expanded, False

    # 2. Common locations
    home = os.path.expanduser("~")
    for base in [home, f"{home}/Desktop", f"{home}/Documents",
                 f"{home}/Downloads", f"{home}/Projects", "/Users"]:
        candidate = os.path.join(base, name)
        if os.path.exists(candidate):
            return candidate, False

    # 3. Spotlight
    found = _spotlight_find(name)
    if found:
        return found, True

    return expanded, False  # return original even if not found


def control(action: str, name: str = "", app: str = "") -> str:
    """Open, list, search, or delete files/folders."""
    print(f"[Tool] Finder: {action} {name}")

    if action == "open":
        if not name:
            subprocess.Popen(["open", os.path.expanduser("~")])
            return "Opened home folder."
        path, via_spotlight = _resolve_path(name)
        if not os.path.exists(path):
            return f"Could not find '{name}' — try a more specific name or check the spelling."
        subprocess.Popen(["open", path])
        hint = f" (found at {path})" if via_spotlight else ""
        return f"Opened {name}{hint}."

    elif action == "open_in_app" and app:
        path, _ = _resolve_path(name)
        subprocess.Popen(["open", "-a", app, path])
        return f"Opened {name} in {app}."

    elif action == "list":
        if not name:
            path = os.path.expanduser("~")
        else:
            path, via_spotlight = _resolve_path(name)
        if not os.path.exists(path):
            return f"Could not find '{name}'. Try spelling it out or saying the full folder name."
        try:
            files = sorted(os.listdir(path))
            result = ", ".join(files[:30])
            hint = f" (at {path})" if name else ""
            return f"Contents of {name or 'home'}{hint}: {result}"
        except Exception as e:
            return str(e)

    elif action == "read_file":
        path, _ = _resolve_path(name)
        if not os.path.exists(path):
            return f"Could not find file '{name}'."
        try:
            with open(path, "r", errors="replace") as f:
                return f.read(8000)
        except Exception as e:
            return str(e)

    elif action == "find":
        # Explicit search — returns all matches with paths
        found = _spotlight_find(name)
        if found:
            return f"Found: {found}"
        return f"No file or folder named '{name}' found on this Mac."

    elif action == "get_desktop_items":
        from tools import applescript
        script = '''
            tell application "Finder"
                set itemList to ""
                repeat with i in (get every item of desktop)
                    set itemList to itemList & (name of i) & linefeed
                end repeat
            end tell
            return itemList
        '''
        result = applescript.run(script)
        return f"Desktop items:\n{result}" if result else "Desktop is empty."

    elif action == "delete":
        path = os.path.expanduser(name)
        subprocess.run(["rm", "-rf", path])
        return f"Deleted {name}."

    return f"Unknown finder action: {action}"

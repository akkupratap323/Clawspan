"""Finder and file/folder operations."""

import os
import subprocess


def control(action: str, name: str = "", app: str = "") -> str:
    """Open, list, or delete files/folders."""
    print(f"[Tool] Finder: {action} {name}")

    if action == "open":
        path = os.path.expanduser(name) if name else os.path.expanduser("~")
        subprocess.run(["open", path])
        return f"Opened {name or 'home folder'}."

    elif action == "open_in_app" and app:
        path = os.path.expanduser(name)
        subprocess.run(["open", "-a", app, path])
        return f"Opened {name} in {app}."

    elif action == "list":
        path = os.path.expanduser(name or "~")
        try:
            files = os.listdir(path)
            return ", ".join(files[:20])
        except Exception as e:
            return str(e)

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

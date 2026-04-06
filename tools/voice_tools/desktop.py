"""Desktop voice tools: Finder, mouse/screen, notifications."""

from __future__ import annotations

from tools import finder, mouse
from tools.vision import describe_screen


def exec_finder_control(action: str, name: str = "", app: str = "", **_kw) -> str:
    """Finder/file operations (open, open_in_app, list, get_desktop_items, delete)."""
    return finder.control(action, name, app)


def exec_mouse_control(action: str, x: int = 0, y: int = 0, target: str = "", **_kw) -> str:
    """Mouse/screen control (find_and_click, find_and_double_click, click, double_click, right_click, move, position)."""
    if action == "find_and_click" and target:
        return mouse.find_and_click(target, double=False)
    if action == "find_and_double_click" and target:
        return mouse.find_and_click(target, double=True)
    if action == "click":
        return mouse.click(x, y)
    if action == "double_click":
        return mouse.double_click(x, y)
    if action == "right_click":
        return mouse.right_click(x, y)
    if action == "move":
        return mouse.move(x, y)
    if action == "position":
        return mouse.position()
    return f"Unknown mouse action: {action}"


def exec_describe_screen(**_kw) -> str:
    """Use AI vision to describe what's currently visible on screen."""
    return describe_screen()


def exec_send_notification(title: str, message: str, **_kw) -> str:
    """Send a macOS notification banner."""
    from tools import applescript
    script = f'display notification "{message}" with title "{title}"'
    applescript.run(script)
    return f"Notification sent: {title}"

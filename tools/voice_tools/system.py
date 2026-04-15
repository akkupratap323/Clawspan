"""System-level voice tools: terminal, apps, Chrome, system control, clipboard."""

from __future__ import annotations

from tools import chrome, clipboard
from tools.apps import open_app, close_app
from tools.system import control as system_control
from tools.terminal import run as run_terminal


def exec_run_terminal(command: str, **_kw) -> str:
    """Run a shell command and return stdout."""
    return run_terminal(command)


def exec_open_app(app_name: str, **_kw) -> str:
    """Open a macOS application by name."""
    return open_app(app_name)


def exec_close_app(app_name: str, **_kw) -> str:
    """Quit a macOS application by name."""
    return close_app(app_name)


def exec_chrome_control(action: str, value: str = "", **_kw) -> str:
    """Control Chrome browser (open_url, new_tab, close_tab, reload, back)."""
    return chrome.control(action, value)


def exec_system_control(action: str, value: int = -1, **_kw) -> str:
    """System control (volume, brightness, sleep, lock, screenshot, mute)."""
    return system_control(action, value)


def exec_clipboard(action: str, text: str = "", **_kw) -> str:
    """Read from or write to the macOS clipboard."""
    if action == "read":
        return clipboard.read()
    if action == "write":
        return clipboard.write(text)
    return f"Unknown clipboard action: {action}"

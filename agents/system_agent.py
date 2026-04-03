"""SystemAgent — Mac control, Chrome, Finder, mouse, apps, system settings, music."""

import subprocess

from core.base_agent import BaseAgent
from tools import applescript, apps, chrome, finder, mouse, system, clipboard
from tools.music import apple_music, yt_music
from tools.vision import describe_screen

SYSTEM_PROMPT = """You handle Mac system control: apps, Chrome, Finder, mouse, volume, music, screenshots.

BROWSER CONTROL:
- "open browser" → chrome_control action "open_url"
- "go to X" → chrome_control action "open_url", value=URL
- "close tab" → chrome_control action "close_tab"
- "new tab" → chrome_control action "new_tab"
- "reload" → chrome_control action "reload"
- "go back" → chrome_control action "back"

MOUSE & SCREEN (CRITICAL):
- "click on X" → mouse_control action "find_and_click", target=X. ALWAYS. No exceptions.
- "what's on my screen" → describe_screen. Only for looking, never clicking.
- "double click on X" → mouse_control action "find_and_double_click", target=X
- "right click at X,Y" → mouse_control action "right_click", x=X, y=Y
- "where is my mouse" → mouse_control action "position"
- NEVER hallucinate coordinates. Only vision tools can see the screen.

MUSIC:
- "play [song]" → yt_music with the song query
- "pause/next/previous/shuffle/current" → music_control with that action
- "volume N" → system_control action "volume_set", value=N

FINDER:
- "open X folder" → finder_control action "open", name=X
- "what's on my desktop" → finder_control action "get_desktop_items"
- "delete X" → finder_control action "delete", name=X

APPS:
- "open [app name]" → open_application with app name

CLIPBOARD:
- "copy X" → clipboard_tool action "write", value=X
- "paste" / "what's in clipboard" → clipboard_tool action "read" """

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "chrome_control",
            "description": "Control Chrome browser. Actions: open_url, new_tab, close_tab, reload, back, get_url, get_title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["open_url", "new_tab", "close_tab", "reload", "back", "get_url", "get_title"]},
                    "value": {"type": "string", "description": "URL or value for the action"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_control",
            "description": "Mouse/screen control. Actions: find_and_click (vision-based click by text), find_and_double_click, click (x,y), double_click (x,y), right_click (x,y), move (x,y), position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["find_and_click", "find_and_double_click", "click", "double_click", "right_click", "move", "position"]},
                    "target": {"type": "string", "description": "Text/element to find on screen (for find_and_click)"},
                    "x": {"type": "integer"}, "y": {"type": "integer"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_screen",
            "description": "Use AI vision to describe what's currently visible on screen.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_control",
            "description": "System control. Actions: volume_up, volume_down, volume_set, mute, sleep, lock, screenshot, brightness_up.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["volume_up", "volume_down", "volume_set", "mute", "sleep", "lock", "screenshot", "brightness_up"]},
                    "value": {"type": "integer", "description": "Value (e.g. volume level 0-100)"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open any macOS application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string"},
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finder_control",
            "description": "Finder/file operations. Actions: open, open_in_app, list, get_desktop_items, delete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["open", "open_in_app", "list", "get_desktop_items", "delete"]},
                    "name": {"type": "string", "description": "File/folder path"},
                    "app": {"type": "string", "description": "App name (for open_in_app)"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "music_control",
            "description": "Apple Music control. Actions: play, pause, next, previous, shuffle, like, current, volume.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["play", "pause", "next", "previous", "shuffle", "like", "current", "volume"]},
                    "query": {"type": "string"},
                    "volume": {"type": "integer"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "yt_music",
            "description": "Play a song/artist on YouTube Music. Use this when user wants to play a specific song.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Song, artist, or playlist name"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal",
            "description": "Run a shell command on macOS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_tool",
            "description": "Clipboard operations. action: 'read' to paste, 'write' to copy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["read", "write"]},
                    "value": {"type": "string", "description": "Text to copy (for write)"},
                },
                "required": ["action"],
            },
        },
    },
]


# ── Tool implementations ─────────────────────────────────────────────────────

def _chrome_control(args: dict) -> str:
    return chrome.control(args["action"], args.get("value", ""))


def _mouse_control(args: dict) -> str:
    action = args["action"]
    if action == "find_and_click":
        return mouse.find_and_click(args.get("target", ""))
    if action == "find_and_double_click":
        return mouse.find_and_click(args.get("target", ""), double=True)
    if action == "click":
        return mouse.click(args.get("x", 0), args.get("y", 0))
    if action == "double_click":
        return mouse.double_click(args.get("x", 0), args.get("y", 0))
    if action == "right_click":
        return mouse.right_click(args.get("x", 0), args.get("y", 0))
    if action == "move":
        return mouse.move(args.get("x", 0), args.get("y", 0))
    if action == "position":
        return mouse.position()
    return f"Unknown mouse action: {action}"


def _describe_screen(_args: dict) -> str:
    return describe_screen()


def _system_control(args: dict) -> str:
    return system.control(args["action"], args.get("value", -1))


def _open_application(args: dict) -> str:
    return apps.open_app(args["app_name"])


def _finder_control(args: dict) -> str:
    return finder.control(args["action"], args.get("name", ""), args.get("app", ""))


def _music_control(args: dict) -> str:
    return apple_music(args["action"], args.get("query", ""), args.get("volume", -1))


def _yt_music(args: dict) -> str:
    return yt_music(args["query"])


def _run_terminal(args: dict) -> str:
    from tools.terminal import run
    return run(args["command"])


def _clipboard_tool(args: dict) -> str:
    if args["action"] == "read":
        return clipboard.read()
    if args["action"] == "write":
        return clipboard.write(args.get("value", ""))
    return f"Unknown clipboard action: {args['action']}"


# ── Agent class ──────────────────────────────────────────────────────────────

class SystemAgent(BaseAgent):
    name = "SystemAgent"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    TOOL_MAP = {
        "chrome_control": _chrome_control,
        "mouse_control": _mouse_control,
        "describe_screen": _describe_screen,
        "system_control": _system_control,
        "open_application": _open_application,
        "finder_control": _finder_control,
        "music_control": _music_control,
        "yt_music": _yt_music,
        "run_terminal": _run_terminal,
        "clipboard_tool": _clipboard_tool,
    }

"""CalendarAgent — Gmail + Google Calendar integration."""

import re
import time
import threading
from datetime import datetime

from core.base_agent import BaseAgent
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from tools.google import (
    gmail_read, gmail_send, gmail_search, gmail_mark_read,
    calendar_list, calendar_create, calendar_delete,
)
from shared.memory import load_memory, save_memory

_COUNT_RE = re.compile(r'\b(\d+)\b')
EMAIL_AUTO_CHECK_INTERVAL = 3600  # 1 hour


def _start_auto_email_checker() -> threading.Thread:
    """Background thread: reads 3 latest emails every hour, saves to memory."""
    def _checker() -> None:
        time.sleep(30)
        while True:
            try:
                gmail_read(max_results=3, query="is:unread")
                mem = load_memory()
                mem["__email_last_check__"] = {
                    "value": f"Auto-checked at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
                save_memory(mem)
            except Exception:
                pass
            time.sleep(EMAIL_AUTO_CHECK_INTERVAL)

    t = threading.Thread(target=_checker, daemon=True, name="EmailAutoChecker")
    t.start()
    return t


SYSTEM_PROMPT = """You handle Gmail and Google Calendar requests.
Keep spoken responses to 2-3 sentences — summarize emails/events concisely.

GMAIL:
- "read my emails" → gmail_read
- "send email to X" → gmail_send
- "find email about X" → gmail_search
- "mark emails as read" → gmail_mark_read

CALENDAR:
- "what's on my calendar" → calendar_list
- "add event X" → calendar_create
- "delete event X" → calendar_delete"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "gmail_read",
            "description": "Read recent emails from Gmail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "description": "Number of emails (default 5)"},
                    "query": {"type": "string", "description": "Gmail search query"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_send",
            "description": "Send an email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_search",
            "description": "Search Gmail with a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_mark_read",
            "description": "Mark emails as read.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Gmail query to match (default is:unread)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list",
            "description": "List upcoming calendar events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Number of days ahead (default 1)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create",
            "description": "Create a calendar event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO 8601 start time"},
                    "end": {"type": "string", "description": "ISO 8601 end time (optional)"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                },
                "required": ["title", "start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_delete",
            "description": "Delete the first upcoming event matching the title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title_query": {"type": "string"},
                },
                "required": ["title_query"],
            },
        },
    },
]


def _gmail_read(args: dict) -> str:
    return gmail_read(args.get("max_results", 5), args.get("query", ""))


def _gmail_send(args: dict) -> str:
    return gmail_send(args["to"], args["subject"], args["body"])


def _gmail_search(args: dict) -> str:
    return gmail_search(args["query"], args.get("max_results", 5))


def _gmail_mark_read(args: dict) -> str:
    return gmail_mark_read(args.get("query", "is:unread"))


def _calendar_list(args: dict) -> str:
    return calendar_list(args.get("days", 1))


def _calendar_create(args: dict) -> str:
    return calendar_create(
        args["title"], args["start"],
        args.get("end", ""), args.get("description", ""), args.get("location", ""),
    )


def _calendar_delete(args: dict) -> str:
    return calendar_delete(args["title_query"])


class CalendarAgent(BaseAgent):
    name = "CalendarAgent"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    TOOL_MAP = {
        "gmail_read": _gmail_read,
        "gmail_send": _gmail_send,
        "gmail_search": _gmail_search,
        "gmail_mark_read": _gmail_mark_read,
        "calendar_list": _calendar_list,
        "calendar_create": _calendar_create,
        "calendar_delete": _calendar_delete,
    }

    def __init__(self) -> None:
        super().__init__()
        self._google_available = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
        if self._google_available:
            _start_auto_email_checker()
            print("[CalendarAgent] Gmail + Calendar connected. Auto-check every 1hr.", flush=True)
        else:
            print("[CalendarAgent] No Google credentials — set GOOGLE_CLIENT_ID/SECRET.", flush=True)

    async def think(self, user_input: str, context: str = "") -> str:
        if not self._google_available:
            return ("Google credentials not configured, sir. "
                    "Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env file.")
        return await super().think(user_input, context=context)

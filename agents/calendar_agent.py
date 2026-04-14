"""CalendarAgent — Gmail + Google Calendar + Personal Care assistant."""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone

from core.base_agent import BaseAgent
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from tools.google import (
    gmail_read, gmail_send, gmail_reply, gmail_search, gmail_mark_read,
    gmail_read_important, gmail_unread_count,
    calendar_list, calendar_create, calendar_update, calendar_delete,
    calendar_daily_brief, calendar_get_events_raw,
)
from shared.memory import load_memory, save_memory

_COUNT_RE = re.compile(r'\b(\d+)\b')

# How often to check for important emails (seconds)
EMAIL_CHECK_INTERVAL   = 900    # 15 min
# How often to push personal care nudges (seconds)
CARE_NUDGE_INTERVAL    = 3600   # 1 hour
# How often to alert for upcoming meetings (seconds)
MEETING_CHECK_INTERVAL = 300    # 5 min


# ── Background threads ────────────────────────────────────────────────────────

def _start_background_watchers(notification_queue=None) -> None:
    """Start all background threads for email + calendar watching."""

    def _email_watcher() -> None:
        """Check every 15 min for important/critical unread emails."""
        time.sleep(60)  # let startup finish first
        seen_ids: set[str] = set()
        while True:
            try:
                important = gmail_read_important(max_results=10)
                for email in important:
                    eid = email["id"]
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        msg = (
                            f"[{email['importance']}] New email: \"{email['subject']}\" "
                            f"from {email['sender'].split('<')[0].strip()}"
                        )
                        print(f"[CalendarAgent] {msg}", flush=True)
                        if notification_queue:
                            from core.awareness import Notification
                            notification_queue.add(Notification(
                                priority=email["importance"],
                                message=msg,
                                source="email",
                            ))
                        # Also fire macOS notification
                        try:
                            import subprocess
                            subprocess.Popen([
                                "osascript", "-e",
                                f'display notification "{email["subject"][:60]}" '
                                f'with title "Important Email" '
                                f'subtitle "{email["sender"].split("<")[0].strip()[:40]}"',
                            ])
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(EMAIL_CHECK_INTERVAL)

    def _meeting_watcher() -> None:
        """Warn 15 and 5 minutes before upcoming meetings."""
        time.sleep(30)
        warned_ids: set[str] = set()
        while True:
            try:
                events = calendar_get_events_raw(days=1)
                now = datetime.now(timezone.utc)
                for e in events:
                    eid = e.get("id", "")
                    start_raw = e["start"].get("dateTime")
                    if not start_raw:
                        continue
                    start_dt = datetime.fromisoformat(start_raw)
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                    minutes_away = (start_dt - now).total_seconds() / 60

                    key_15 = f"{eid}_15"
                    key_5  = f"{eid}_5"

                    meet_link = ""
                    for ep in e.get("conferenceData", {}).get("entryPoints", []):
                        if ep.get("entryPointType") == "video":
                            meet_link = ep.get("uri", "")
                            break

                    if 13 < minutes_away <= 16 and key_15 not in warned_ids:
                        warned_ids.add(key_15)
                        title = e.get("summary", "Meeting")
                        msg = f"Meeting in 15 minutes: {title}"
                        if meet_link:
                            msg += f" — {meet_link}"
                        _fire_notification("Meeting Soon", msg, priority="HIGH",
                                           queue=notification_queue)

                    elif 3 < minutes_away <= 6 and key_5 not in warned_ids:
                        warned_ids.add(key_5)
                        title = e.get("summary", "Meeting")
                        msg = f"Meeting in 5 minutes: {title}"
                        if meet_link:
                            msg += f" — {meet_link}"
                        _fire_notification("Meeting NOW", msg, priority="CRITICAL",
                                           queue=notification_queue)

            except Exception:
                pass
            time.sleep(MEETING_CHECK_INTERVAL)

    def _care_nudger() -> None:
        """Personal care nudges — hydration, breaks, posture."""
        time.sleep(120)
        nudge_idx = 0
        nudges = [
            ("Hydration", "Time to drink some water, boss. Stay sharp."),
            ("Break", "You've been at it a while. Stretch for 2 minutes."),
            ("Posture", "Check your posture. Sit up straight."),
            ("Eyes", "Look away from the screen for 20 seconds."),
        ]
        while True:
            try:
                nudge_title, nudge_msg = nudges[nudge_idx % len(nudges)]
                nudge_idx += 1
                import subprocess
                subprocess.Popen([
                    "osascript", "-e",
                    f'display notification "{nudge_msg}" '
                    f'with title "Clawspan — {nudge_title}"',
                ])
            except Exception:
                pass
            time.sleep(CARE_NUDGE_INTERVAL)

    for fn, name in [
        (_email_watcher,  "EmailWatcher"),
        (_meeting_watcher,"MeetingWatcher"),
        (_care_nudger,    "CareNudger"),
    ]:
        t = threading.Thread(target=fn, daemon=True, name=name)
        t.start()
        print(f"[CalendarAgent] {name} started.", flush=True)


def _fire_notification(title: str, message: str, priority: str = "HIGH",
                       queue=None) -> None:
    """Push macOS notification + add to awareness queue."""
    try:
        import subprocess
        subprocess.Popen([
            "osascript", "-e",
            f'display notification "{message[:120]}" with title "{title}"',
        ])
    except Exception:
        pass
    if queue:
        try:
            from core.awareness import Notification
            queue.add(Notification(priority=priority, message=message, source="calendar"))
        except Exception:
            pass


# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Clawspan's personal calendar and communications assistant.

Your responsibilities:
1. Gmail — read, search, send, reply, and alert about important emails
2. Google Calendar — list, create, update, delete events
3. Google Meet — schedule meetings with auto-generated Meet links, share via email
4. Daily briefings — "what's my day look like", "what's on this week"
5. Personal care — remind about water, breaks, posture (already running in background)

Response style:
- Concise spoken summaries (2-4 sentences for voice)
- When sharing a Meet link, read it clearly or say "I've sent it to your email"
- For important emails, always state the sender and subject
- For scheduling, always confirm the exact date/time back to the user

GMAIL actions: read, search, send, reply, mark_read, important, unread_count
CALENDAR actions: list, brief, today, week, find, create, schedule_meet, update, delete

Scheduling Google Meet example:
  User: "Schedule a call with john@example.com tomorrow at 3pm"
  → calendar action=schedule_meet, title="Call", start="2026-04-14T15:00:00",
    attendees="john@example.com"
  → This creates the event, generates a Meet link, AND emails john the invite.

Important mail alerts are automatic — you don't need to poll, they surface proactively."""


# ── Tool schemas ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "gmail_read",
            "description": "Read recent emails. Use query for filtering (e.g. 'is:unread', 'from:contact@example.com').",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 5},
                    "query": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_send",
            "description": "Send a new email.",
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
            "name": "gmail_reply",
            "description": "Reply to an existing email thread.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Gmail message ID to reply to"},
                    "body": {"type": "string"},
                },
                "required": ["message_id", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_search",
            "description": "Search Gmail by keyword, sender, or label.",
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
                    "query": {"type": "string", "default": "is:unread"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_important",
            "description": "Fetch only HIGH/CRITICAL importance unread emails.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 10},
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
                    "days": {"type": "integer", "default": 1},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_brief",
            "description": "Get a daily briefing of today's or this week's schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 1},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create",
            "description": (
                "Create a calendar event. Set with_meet=true to add Google Meet. "
                "Set attendees as comma-separated emails to invite people."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title":       {"type": "string"},
                    "start":       {"type": "string", "description": "ISO 8601 e.g. 2026-04-14T15:00:00"},
                    "end":         {"type": "string"},
                    "description": {"type": "string"},
                    "location":    {"type": "string"},
                    "with_meet":   {"type": "boolean", "default": False},
                    "attendees":   {"type": "string", "description": "Comma-separated email addresses"},
                    "send_invite": {"type": "string", "description": "Set to 'yes' to email invites"},
                },
                "required": ["title", "start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_schedule_meet",
            "description": (
                "Schedule a Google Meet call. Creates event with Meet link AND "
                "emails the Meet link to all attendees automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title":       {"type": "string"},
                    "start":       {"type": "string"},
                    "end":         {"type": "string"},
                    "attendees":   {"type": "string", "description": "Comma-separated emails"},
                    "description": {"type": "string"},
                },
                "required": ["title", "start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_update",
            "description": "Update an existing event (reschedule, rename, change location).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title_query":      {"type": "string", "description": "Current event title to find"},
                    "new_title":        {"type": "string"},
                    "new_start":        {"type": "string"},
                    "new_end":          {"type": "string"},
                    "new_description":  {"type": "string"},
                    "new_location":     {"type": "string"},
                },
                "required": ["title_query"],
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


# ── Tool dispatch ─────────────────────────────────────────────────────────────

def _gmail_read(args: dict) -> str:
    return gmail_read(args.get("max_results", 5), args.get("query", ""))

def _gmail_send(args: dict) -> str:
    return gmail_send(args["to"], args["subject"], args["body"])

def _gmail_reply(args: dict) -> str:
    return gmail_reply(args["message_id"], args["body"])

def _gmail_search(args: dict) -> str:
    return gmail_search(args["query"], args.get("max_results", 5))

def _gmail_mark_read(args: dict) -> str:
    return gmail_mark_read(args.get("query", "is:unread"))

def _gmail_important(args: dict) -> str:
    emails = gmail_read_important(args.get("max_results", 10))
    if not emails:
        return "No important unread emails right now."
    lines = []
    for e in emails:
        lines.append(
            f"[{e['importance']}] {e['subject']}\n"
            f"  From: {e['sender']}\n"
            f"  {e['snippet'][:150]}"
        )
    return "\n\n".join(lines)

def _calendar_list(args: dict) -> str:
    return calendar_list(args.get("days", 1))

def _calendar_brief(args: dict) -> str:
    return calendar_daily_brief(args.get("days", 1))

def _calendar_create(args: dict) -> str:
    from tools.voice_tools.comms import _parse_attendees, _send_meet_invite
    attendee_list = _parse_attendees(args.get("attendees", ""))
    result = calendar_create(
        title=args["title"],
        start=args["start"],
        end=args.get("end", ""),
        description=args.get("description", ""),
        location=args.get("location", ""),
        with_meet=args.get("with_meet", False),
        attendees=attendee_list,
    )
    if args.get("send_invite", "").lower() == "yes" and attendee_list:
        _send_meet_invite(args["title"], args["start"], result, attendee_list)
    return result

def _calendar_schedule_meet(args: dict) -> str:
    from tools.voice_tools.comms import _parse_attendees, _send_meet_invite
    attendee_list = _parse_attendees(args.get("attendees", ""))
    result = calendar_create(
        title=args["title"],
        start=args["start"],
        end=args.get("end", ""),
        description=args.get("description", ""),
        location="",
        with_meet=True,
        attendees=attendee_list,
    )
    if attendee_list:
        _send_meet_invite(args["title"], args["start"], result, attendee_list)
    return result

def _calendar_update(args: dict) -> str:
    return calendar_update(
        title_query=args["title_query"],
        new_title=args.get("new_title", ""),
        new_start=args.get("new_start", ""),
        new_end=args.get("new_end", ""),
        new_description=args.get("new_description", ""),
        new_location=args.get("new_location", ""),
    )

def _calendar_delete(args: dict) -> str:
    return calendar_delete(args["title_query"])


# ── Agent class ───────────────────────────────────────────────────────────────

class CalendarAgent(BaseAgent):
    name = "CalendarAgent"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    TOOL_MAP = {
        "gmail_read":            _gmail_read,
        "gmail_send":            _gmail_send,
        "gmail_reply":           _gmail_reply,
        "gmail_search":          _gmail_search,
        "gmail_mark_read":       _gmail_mark_read,
        "gmail_important":       _gmail_important,
        "calendar_list":         _calendar_list,
        "calendar_brief":        _calendar_brief,
        "calendar_create":       _calendar_create,
        "calendar_schedule_meet":_calendar_schedule_meet,
        "calendar_update":       _calendar_update,
        "calendar_delete":       _calendar_delete,
    }

    def __init__(self, notification_queue=None) -> None:
        super().__init__()
        self._google_available = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
        self._notification_queue = notification_queue
        if self._google_available:
            _start_background_watchers(notification_queue)
            print("[CalendarAgent] Gmail + Calendar + Meet ready.", flush=True)
        else:
            print("[CalendarAgent] No Google credentials — set GOOGLE_CLIENT_ID/SECRET.", flush=True)

    async def think(self, user_input: str, context: str = "") -> str:
        if not self._google_available:
            return (
                "Google credentials not configured, boss. "
                "Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env."
            )
        return await super().think(user_input, context=context)

"""Communication voice tools: Gmail + Google Calendar (full-featured)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from tools.google import (
    gmail_read,
    gmail_send,
    gmail_reply,
    gmail_search,
    gmail_mark_read,
    calendar_list,
    calendar_create,
    calendar_update,
    calendar_delete,
    calendar_daily_brief,
)


# ── Gmail ─────────────────────────────────────────────────────────────────────

def exec_gmail(
    action: str,
    query: str = "",
    to: str = "",
    subject: str = "",
    body: str = "",
    message_id: str = "",
    max_results: int = 5,
    **_kw,
) -> str:
    """Gmail operations.

    Actions:
      read        — read recent emails (query optional, e.g. "is:unread")
      search      — search by keyword/sender/label
      send        — send a new email (to, subject, body required)
      reply       — reply to a thread (message_id, body required)
      mark_read   — mark matching emails as read
      important   — show only HIGH/CRITICAL unread emails
      unread_count— how many unread emails
    """
    if action == "read":
        return gmail_read(max_results=max_results, query=query)

    if action == "search":
        if not query:
            return "Need a 'query' to search emails."
        return gmail_search(query=query, max_results=max_results)

    if action == "send":
        if not to or not subject or not body:
            return "Need 'to', 'subject', and 'body' to send an email."
        return gmail_send(to=to, subject=subject, body=body)

    if action == "reply":
        if not message_id or not body:
            return "Need 'message_id' and 'body' to reply."
        return gmail_reply(message_id=message_id, body=body)

    if action == "mark_read":
        return gmail_mark_read(query=query or "is:unread")

    if action == "important":
        from tools.google import gmail_read_important
        emails = gmail_read_important(max_results=max_results)
        if not emails:
            return "No important or critical unread emails right now."
        lines = []
        for e in emails:
            lines.append(
                f"[{e['importance']}] {e['subject']}\n"
                f"  From: {e['sender']}\n"
                f"  {e['snippet'][:150]}"
            )
        return "\n\n".join(lines)

    if action == "unread_count":
        from tools.google import gmail_unread_count
        count = gmail_unread_count()
        return f"You have {count} unread emails."

    return f"Unknown gmail action: {action}. Use: read, search, send, reply, mark_read, important, unread_count"


# ── Calendar ──────────────────────────────────────────────────────────────────

def _parse_attendees(attendees_str: str) -> list[str]:
    """Parse comma-separated or space-separated email list."""
    if not attendees_str:
        return []
    return [e.strip() for e in re.split(r"[,\s]+", attendees_str) if "@" in e]


def exec_calendar(
    action: str,
    days: int = 1,
    title: str = "",
    start: str = "",
    end: str = "",
    description: str = "",
    location: str = "",
    with_meet: bool = False,
    attendees: str = "",
    new_title: str = "",
    new_start: str = "",
    new_end: str = "",
    send_invite: str = "",
    **_kw,
) -> str:
    """Google Calendar operations.

    Actions:
      list         — list events (days=N ahead)
      brief        — daily briefing summary (spoken-friendly)
      create       — create event (with_meet=true for Google Meet)
      schedule_meet— shortcut: create an event with Google Meet link
      update       — update an existing event by title
      delete       — delete event by title
      today        — what's on today
      week         — events this week
      find         — search for an event by keyword
    """
    attendee_list = _parse_attendees(attendees)

    # ── list ────────────────────────────────────────────────────────────────
    if action == "list":
        return calendar_list(days=days)

    # ── brief ───────────────────────────────────────────────────────────────
    if action == "brief":
        return calendar_daily_brief(days=days)

    # ── today ───────────────────────────────────────────────────────────────
    if action == "today":
        return calendar_daily_brief(days=1)

    # ── week ────────────────────────────────────────────────────────────────
    if action == "week":
        return calendar_list(days=7)

    # ── find ────────────────────────────────────────────────────────────────
    if action == "find":
        if not title:
            return "Need 'title' keyword to search events."
        # calendar_list with a text search
        from tools.google import _calendar, datetime as _dt, timezone as _tz, timedelta as _td
        from datetime import datetime as dt, timezone as tz, timedelta as td
        now = datetime.now(timezone.utc)
        end_dt = now + timedelta(days=30)
        results = _calendar().events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end_dt.isoformat(),
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
            q=title,
        ).execute()
        events = results.get("items", [])
        if not events:
            return f"No events matching '{title}' in the next 30 days."
        lines = []
        for e in events:
            start_raw = e["start"].get("dateTime", e["start"].get("date", "?"))
            try:
                start_str = datetime.fromisoformat(start_raw).strftime("%a %b %d, %I:%M %p")
            except Exception:
                start_str = start_raw
            lines.append(f"- {start_str}: {e.get('summary', 'Untitled')}")
        return "\n".join(lines)

    # ── create ──────────────────────────────────────────────────────────────
    if action == "create":
        if not title or not start:
            return "Need 'title' and 'start' to create an event."
        result = calendar_create(
            title=title,
            start=start,
            end=end,
            description=description,
            location=location,
            with_meet=with_meet,
            attendees=attendee_list,
        )
        # Send invite email with Meet link if requested
        if send_invite and attendee_list:
            _send_meet_invite(title, start, result, attendee_list)
        return result

    # ── schedule_meet ────────────────────────────────────────────────────────
    if action == "schedule_meet":
        if not title or not start:
            return "Need 'title' and 'start' to schedule a Google Meet."
        result = calendar_create(
            title=title,
            start=start,
            end=end,
            description=description,
            location=location,
            with_meet=True,
            attendees=attendee_list,
        )
        # Auto-send invite emails to attendees
        if attendee_list:
            _send_meet_invite(title, start, result, attendee_list)
        return result

    # ── update ──────────────────────────────────────────────────────────────
    if action == "update":
        if not title:
            return "Need 'title' (current name) to update an event."
        return calendar_update(
            title_query=title,
            new_title=new_title,
            new_start=new_start,
            new_end=new_end,
            new_description=description,
            new_location=location,
        )

    # ── delete ──────────────────────────────────────────────────────────────
    if action == "delete":
        if not title:
            return "Need 'title' to delete an event."
        return calendar_delete(title_query=title)

    return (
        f"Unknown calendar action: {action}. "
        "Use: list, brief, today, week, find, create, schedule_meet, update, delete"
    )


def _send_meet_invite(title: str, start: str, create_result: str, attendees: list[str]) -> None:
    """Email Google Meet link to all attendees after event creation."""
    # Extract Meet link from the create result string
    meet_link = ""
    for line in create_result.split("\n"):
        if "meet.google.com" in line or "Google Meet:" in line:
            parts = line.split(":", 1)
            if len(parts) > 1:
                meet_link = parts[1].strip()
            else:
                meet_link = line.strip()
            break

    if not meet_link:
        return

    try:
        start_dt = datetime.fromisoformat(start)
        time_str = start_dt.strftime("%B %d, %Y at %I:%M %p IST")
    except Exception:
        time_str = start

    subject = f"Invite: {title}"
    body = (
        f"You're invited to: {title}\n"
        f"When: {time_str}\n\n"
        f"Join Google Meet: {meet_link}\n\n"
        f"This invite was sent by Clawspan."
    )

    for email in attendees:
        try:
            gmail_send(to=email, subject=subject, body=body)
        except Exception:
            pass

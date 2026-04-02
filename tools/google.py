"""Google services — Gmail + Calendar."""

import base64
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

from auth.google import get_credentials as _get_credentials

# ── Lazy service caches ──────────────────────────────────────────────────────

_gmail_svc = None
_calendar_svc = None


def _gmail():
    """Lazy Gmail service."""
    global _gmail_svc
    if _gmail_svc is None:
        from googleapiclient.discovery import build
        _gmail_svc = build("gmail", "v1", credentials=_get_credentials())
    return _gmail_svc


def _calendar():
    """Lazy Calendar service."""
    global _calendar_svc
    if _calendar_svc is None:
        from googleapiclient.discovery import build
        _calendar_svc = build("calendar", "v3", credentials=_get_credentials())
    return _calendar_svc


def _get_header(headers: list, name: str) -> str:
    """Extract a header value by name."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode_email_body(payload: dict) -> str:
    """Extract plain text body from Gmail message payload."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    break
            elif "parts" in part:
                body = _decode_email_body(part)
                if body:
                    break
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return body.strip()


# ── Gmail ────────────────────────────────────────────────────────────────────

def gmail_read(max_results: int = 5, query: str = "") -> str:
    """Read recent emails."""
    q = query or "is:unread"
    results = _gmail().users().messages().list(
        userId="me", q=q, maxResults=max_results,
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        return "No emails found."

    summaries = []
    for m in messages:
        msg = _gmail().users().messages().get(
            userId="me", id=m["id"], format="full",
        ).execute()
        headers = msg.get("payload", {}).get("headers", [])
        subject = _get_header(headers, "subject") or "(no subject)"
        sender = _get_header(headers, "from") or "unknown"
        date = _get_header(headers, "date") or ""
        snippet = msg.get("snippet", "")[:150]
        summaries.append(
            f"From: {sender}\n  Subject: {subject}\n  Date: {date}\n  Preview: {snippet}"
        )

    return "\n\n".join(summaries)


def gmail_send(to: str, subject: str, body: str) -> str:
    """Send an email."""
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    _gmail().users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Email sent to {to}."


def gmail_search(query: str, max_results: int = 5) -> str:
    """Search Gmail."""
    return gmail_read(max_results=max_results, query=query)


def gmail_mark_read(query: str = "is:unread") -> str:
    """Mark emails matching query as read."""
    results = _gmail().users().messages().list(
        userId="me", q=query, maxResults=20,
    ).execute()
    messages = results.get("messages", [])
    if not messages:
        return "No matching emails."
    for m in messages:
        _gmail().users().messages().modify(
            userId="me", id=m["id"],
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    return f"Marked {len(messages)} email(s) as read."


# ── Calendar ─────────────────────────────────────────────────────────────────

def calendar_list(days: int = 1) -> str:
    """List upcoming events for the next N days."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    events_result = _calendar().events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        maxResults=10,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    if not events:
        return f"No events in the next {days} day(s)."

    lines = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date", "?"))
        try:
            dt = datetime.fromisoformat(start)
            start_str = dt.strftime("%a %b %d, %I:%M %p")
        except Exception:
            start_str = start
        summary = e.get("summary", "Untitled")
        location = e.get("location", "")
        loc_str = f" @ {location}" if location else ""
        lines.append(f"- {start_str}: {summary}{loc_str}")

    return "\n".join(lines)


def calendar_create(
    title: str,
    start: str,
    end: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """Create a calendar event. start/end: ISO 8601 strings."""
    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError:
        return f"Invalid start time: {start}. Use format like 2025-04-10T14:00:00"

    if not end:
        end_dt = start_dt + timedelta(hours=1)
        end = end_dt.isoformat()

    if "T" not in start:
        event_body = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"date": start},
            "end": {"date": end or start},
        }
    else:
        event_body = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start, "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end, "timeZone": "Asia/Kolkata"},
        }

    event = _calendar().events().insert(
        calendarId="primary", body=event_body,
    ).execute()
    return f"Event '{title}' created: {event.get('htmlLink', 'done')}."


def calendar_delete(title_query: str) -> str:
    """Delete the first upcoming event matching the title."""
    now = datetime.now(timezone.utc)
    events_result = _calendar().events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
        q=title_query,
    ).execute()

    events = events_result.get("items", [])
    if not events:
        return f"No upcoming event matching '{title_query}'."

    event = events[0]
    _calendar().events().delete(
        calendarId="primary", eventId=event["id"],
    ).execute()
    return f"Deleted event: '{event.get('summary', title_query)}'."

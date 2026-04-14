"""Google services — Gmail + Google Calendar."""

from __future__ import annotations

import base64
import re
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from auth.google import get_credentials as _get_credentials

# ── Lazy service caches ──────────────────────────────────────────────────────

_gmail_svc = None
_calendar_svc = None


def _gmail(force_rebuild: bool = False):
    """Lazy Gmail service — rebuilds on SSL/connection errors."""
    global _gmail_svc
    if _gmail_svc is None or force_rebuild:
        from googleapiclient.discovery import build
        _gmail_svc = build("gmail", "v1", credentials=_get_credentials())
    return _gmail_svc


def _calendar(force_rebuild: bool = False):
    """Lazy Calendar service — rebuilds on SSL/connection errors."""
    global _calendar_svc
    if _calendar_svc is None or force_rebuild:
        from googleapiclient.discovery import build
        _calendar_svc = build("calendar", "v3", credentials=_get_credentials())
    return _calendar_svc


def _is_ssl_error(e: Exception) -> bool:
    """Check if an exception is SSL/connection related."""
    msg = str(e).lower()
    return any(x in msg for x in ("ssl", "record layer", "connection", "eof", "broken pipe", "reset"))


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


def _classify_email_importance(subject: str, sender: str, snippet: str) -> str:
    """Classify email importance: CRITICAL / HIGH / MEDIUM / LOW.

    Signals:
      CRITICAL — payment failed, security alert, account suspended, legal
      HIGH     — investor/VC, job offer, deadline, interview, urgent
      MEDIUM   — newsletters from known senders, GitHub notifications
      LOW      — marketing, promotions
    """
    text = f"{subject} {sender} {snippet}".lower()

    critical_signals = [
        "payment failed", "invoice overdue", "account suspended",
        "security alert", "unauthorized access", "password reset",
        "legal notice", "lawsuit", "urgent action required",
        "your account has been", "suspicious activity",
    ]
    high_signals = [
        "investor", "term sheet", "funding", "acquisition", "partnership",
        "interview", "job offer", "deadline", "urgent", "asap",
        "follow up", "follow-up", "action required", "please respond",
        "board", "contract", "agreement", "nda", "proposal",
    ]
    low_signals = [
        "unsubscribe", "no-reply", "noreply", "newsletter", "promotion",
        "sale", "discount", "coupon", "offer expires", "marketing",
        "donotreply", "notifications@", "updates@", "info@",
    ]

    for s in critical_signals:
        if s in text:
            return "CRITICAL"
    for s in high_signals:
        if s in text:
            return "HIGH"
    for s in low_signals:
        if s in text:
            return "LOW"
    return "MEDIUM"


# ── Gmail ────────────────────────────────────────────────────────────────────

def gmail_read(max_results: int = 5, query: str = "") -> str:
    """Read recent emails with importance classification. Auto-reconnects on SSL errors."""
    q = query or "is:unread"
    for attempt in range(2):
        try:
            results = _gmail(force_rebuild=(attempt > 0)).users().messages().list(
                userId="me", q=q, maxResults=max_results,
            ).execute()
            break
        except Exception as e:
            if attempt == 0 and _is_ssl_error(e):
                continue  # retry with fresh service
            return f"Could not read emails: {e}"

    messages = results.get("messages", [])
    if not messages:
        return "No emails found."

    summaries = []
    for m in messages:
        try:
            msg = _gmail().users().messages().get(
                userId="me", id=m["id"], format="full",
            ).execute()
        except Exception:
            continue
        headers = msg.get("payload", {}).get("headers", [])
        subject = _get_header(headers, "subject") or "(no subject)"
        sender = _get_header(headers, "from") or "unknown"
        date = _get_header(headers, "date") or ""
        snippet = msg.get("snippet", "")[:200]
        importance = _classify_email_importance(subject, sender, snippet)
        summaries.append(
            f"[{importance}] From: {sender}\n"
            f"  Subject: {subject}\n"
            f"  Date: {date}\n"
            f"  Preview: {snippet}"
        )

    return "\n\n".join(summaries) if summaries else "No emails found."


def gmail_read_important(max_results: int = 10) -> list[dict]:
    """Return list of important/critical unread emails as dicts for proactive alerts."""
    for attempt in range(2):
        try:
            results = _gmail(force_rebuild=(attempt > 0)).users().messages().list(
                userId="me", q="is:unread", maxResults=max_results,
            ).execute()
            break
        except Exception as e:
            if attempt == 0 and _is_ssl_error(e):
                continue
            return []

    messages = results.get("messages", [])
    important = []

    for m in messages:
        msg = _gmail().users().messages().get(
            userId="me", id=m["id"], format="full",
        ).execute()
        headers = msg.get("payload", {}).get("headers", [])
        subject = _get_header(headers, "subject") or "(no subject)"
        sender = _get_header(headers, "from") or "unknown"
        date = _get_header(headers, "date") or ""
        snippet = msg.get("snippet", "")[:300]
        importance = _classify_email_importance(subject, sender, snippet)

        if importance in ("CRITICAL", "HIGH"):
            important.append({
                "id": m["id"],
                "subject": subject,
                "sender": sender,
                "date": date,
                "snippet": snippet,
                "importance": importance,
            })

    return important


def gmail_send(to: str, subject: str, body: str) -> str:
    """Send an email."""
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    _gmail().users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Email sent to {to}."


def gmail_reply(message_id: str, body: str) -> str:
    """Reply to an existing email thread."""
    # Fetch original to get headers
    orig = _gmail().users().messages().get(
        userId="me", id=message_id, format="full",
    ).execute()
    headers = orig.get("payload", {}).get("headers", [])
    to = _get_header(headers, "from")
    subject = _get_header(headers, "subject")
    thread_id = orig.get("threadId", "")

    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject

    # Preserve thread
    msg["In-Reply-To"] = _get_header(headers, "message-id")
    msg["References"] = _get_header(headers, "message-id")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    _gmail().users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": thread_id},
    ).execute()
    return f"Reply sent to {to}."


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


def gmail_unread_count() -> int:
    """Return count of unread emails."""
    result = _gmail().users().getProfile(userId="me").execute()
    return result.get("messagesTotal", 0)


# ── Calendar ─────────────────────────────────────────────────────────────────

def calendar_list(days: int = 1) -> str:
    """List upcoming events for the next N days."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    for attempt in range(2):
        try:
            events_result = _calendar(force_rebuild=(attempt > 0)).events().list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=end.isoformat(),
                maxResults=20,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            break
        except Exception as e:
            if attempt == 0 and _is_ssl_error(e):
                continue
            return f"Could not fetch calendar: {e}"

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

        # Show Google Meet link if present
        meet_link = ""
        conf = e.get("conferenceData", {})
        for ep in conf.get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                meet_link = f" | Meet: {ep.get('uri', '')}"
                break

        lines.append(f"- {start_str}: {summary}{loc_str}{meet_link}")

    return "\n".join(lines)


def calendar_get_events_raw(days: int = 7) -> list[dict]:
    """Return raw event dicts for the next N days (for awareness checks)."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    events_result = _calendar().events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        maxResults=50,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return events_result.get("items", [])


def calendar_create(
    title: str,
    start: str,
    end: str = "",
    description: str = "",
    location: str = "",
    with_meet: bool = False,
    attendees: list[str] | None = None,
) -> str:
    """Create a calendar event, optionally with Google Meet + attendees.

    Args:
        title: Event title
        start: ISO 8601 start time (e.g. 2026-04-14T15:00:00)
        end: ISO 8601 end time (defaults to start + 1 hour)
        description: Event description
        location: Physical location
        with_meet: If True, attach a Google Meet conference
        attendees: List of email addresses to invite
    """
    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError:
        return f"Invalid start time: {start}. Use format like 2026-04-14T15:00:00"

    if not end:
        end_dt = start_dt + timedelta(hours=1)
        end = end_dt.isoformat()

    is_datetime = "T" in start

    if is_datetime:
        event_body: dict[str, Any] = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start, "timeZone": "Asia/Kolkata"},
            "end":   {"dateTime": end,   "timeZone": "Asia/Kolkata"},
        }
    else:
        event_body = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"date": start},
            "end":   {"date": end or start},
        }

    # Google Meet conference
    if with_meet and is_datetime:
        import uuid
        event_body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    # Attendees
    if attendees:
        event_body["attendees"] = [{"email": e.strip()} for e in attendees if e.strip()]

    insert_kwargs: dict[str, Any] = {"calendarId": "primary", "body": event_body}
    if with_meet:
        insert_kwargs["conferenceDataVersion"] = 1

    event = _calendar().events().insert(**insert_kwargs).execute()

    # Extract Meet link
    meet_link = ""
    conf = event.get("conferenceData", {})
    for ep in conf.get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            meet_link = ep.get("uri", "")
            break

    result = f"Event '{title}' created."
    if meet_link:
        result += f"\nGoogle Meet: {meet_link}"
    result += f"\nCalendar link: {event.get('htmlLink', '')}"

    return result


def calendar_update(
    title_query: str,
    new_title: str = "",
    new_start: str = "",
    new_end: str = "",
    new_description: str = "",
    new_location: str = "",
) -> str:
    """Update the first upcoming event matching title_query."""
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

    event = dict(events[0])  # copy — don't mutate original

    if new_title:
        event["summary"] = new_title
    if new_description:
        event["description"] = new_description
    if new_location:
        event["location"] = new_location
    if new_start:
        if "T" in new_start:
            event["start"] = {"dateTime": new_start, "timeZone": "Asia/Kolkata"}
            if not new_end:
                start_dt = datetime.fromisoformat(new_start)
                new_end = (start_dt + timedelta(hours=1)).isoformat()
            event["end"] = {"dateTime": new_end, "timeZone": "Asia/Kolkata"}
        else:
            event["start"] = {"date": new_start}
            event["end"] = {"date": new_end or new_start}
    elif new_end:
        if "T" in new_end:
            event["end"] = {"dateTime": new_end, "timeZone": "Asia/Kolkata"}
        else:
            event["end"] = {"date": new_end}

    updated = _calendar().events().update(
        calendarId="primary", eventId=event["id"], body=event,
    ).execute()
    return f"Updated event: '{updated.get('summary', title_query)}'."


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


def calendar_daily_brief(days: int = 1) -> str:
    """Return a formatted daily briefing of upcoming events."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    events_result = _calendar().events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    date_label = "Today" if days == 1 else f"Next {days} days"

    if not events:
        return f"{date_label}: Nothing scheduled. Clear day."

    lines = [f"--- {date_label}'s Schedule ---"]
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date", "?"))
        try:
            dt = datetime.fromisoformat(start)
            t = dt.strftime("%I:%M %p")
        except Exception:
            t = start
        summary = e.get("summary", "Untitled")
        attendees = e.get("attendees", [])
        n_attendees = len(attendees)
        attendee_str = f" ({n_attendees} attendees)" if n_attendees > 1 else ""

        meet_link = ""
        for ep in e.get("conferenceData", {}).get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                meet_link = f" — {ep['uri']}"
                break

        lines.append(f"  {t}  {summary}{attendee_str}{meet_link}")

    return "\n".join(lines)

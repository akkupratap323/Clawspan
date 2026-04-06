"""Communication voice tools: Gmail + Google Calendar."""

from __future__ import annotations

from tools.google import (
    gmail_read, gmail_send, gmail_search, gmail_mark_read,
    calendar_list, calendar_create, calendar_delete,
)


def exec_gmail(action: str, query: str = "", to: str = "", subject: str = "",
               body: str = "", max_results: int = 5, **_kw) -> str:
    """Gmail operations (read, search, send, mark_read)."""
    if action == "read":
        return gmail_read(max_results=max_results, query=query)
    if action == "search":
        return gmail_search(query=query, max_results=max_results)
    if action == "send":
        if not to or not subject or not body:
            return "Need 'to', 'subject', and 'body' to send an email."
        return gmail_send(to=to, subject=subject, body=body)
    if action == "mark_read":
        return gmail_mark_read(query=query or "is:unread")
    return f"Unknown gmail action: {action}"


def exec_calendar(action: str, days: int = 1, title: str = "", start: str = "",
                  end: str = "", description: str = "", location: str = "", **_kw) -> str:
    """Google Calendar operations (list, create, delete events)."""
    if action == "list":
        return calendar_list(days=days)
    if action == "create":
        if not title or not start:
            return "Need 'title' and 'start' to create an event."
        return calendar_create(title=title, start=start, end=end,
                               description=description, location=location)
    if action == "delete":
        if not title:
            return "Need 'title' to delete an event."
        return calendar_delete(title_query=title)
    return f"Unknown calendar action: {action}"

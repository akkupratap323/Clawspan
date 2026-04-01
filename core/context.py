"""SessionContext — the shared context bus (nervous system).

A single session context object shared across all agents.
Stores recent turns, state flags, and derived facts so no agent is ever "cold."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Regexes to extract state changes from agent responses / tool calls
_STATE_PATTERNS = [
    # App launches
    (r"Opened\s+(.+)", "last_app"),
    # Chrome navigation
    (r"Navigated?\s+to\s+(.+)", "last_url"),
    # Email context
    (r"(?:Email|Message)\s+from\s+([^\s,]+(?:\s+[^\s,]+)?)", "last_email_from"),
    # Calendar
    (r"(?:Created|Scheduled|Added)\s+(?:event\s+)?(.+)", "last_event"),
    # Search
    (r"Searched?\s+(?:for\s+)?(.+)", "last_search"),
]

# Keywords that imply state
_APP_VERBS = {"opened", "launched", "started", "switched to", "focused"}
_CHROME_VERBS = {"navigated", "opened url", "went to", "loaded"}
_SEARCH_VERBS = {"searched", "looked up", "googled", "found"}


@dataclass
class TurnEntry:
    """One conversation turn."""
    timestamp: str
    user_input: str
    agent_used: str
    response_summary: str
    tool_calls: list[str] = field(default_factory=list)


class SessionContext:
    """Shared context bus — all agents read/write through this."""

    MAX_TURNS = 10       # keep last N turns
    CONTEXT_INJECT = 5   # inject last N turns into agent prompts

    def __init__(self) -> None:
        self._turns: list[TurnEntry] = []
        self._state: dict[str, Any] = {}  # chrome_open, last_app, last_url, etc.

    # ── Turn management ──────────────────────────────────────────────────

    def add_turn(
        self,
        user_input: str,
        agent_used: str,
        response_summary: str,
        tool_calls: list[str] | None = None,
    ) -> None:
        """Record a completed turn and update state."""
        entry = TurnEntry(
            timestamp=datetime.now().strftime("%H:%M"),
            user_input=user_input[:120],
            agent_used=agent_used,
            response_summary=response_summary[:120],
            tool_calls=tool_calls or [],
        )
        self._turns.append(entry)
        if len(self._turns) > self.MAX_TURNS:
            self._turns = self._turns[-self.MAX_TURNS:]

        # Update state flags from response + tool calls
        self._update_state(response_summary, tool_calls or [], user_input)

    # ── State extraction ─────────────────────────────────────────────────

    def _update_state(
        self, response: str, tool_calls: list[str], user_input: str
    ) -> None:
        """Extract state changes from tool calls and response text."""
        lower_response = response.lower()
        lower_input = user_input.lower()

        # Chrome state
        if any(t in tool_calls for t in ("chrome_control",)):
            self._state["chrome_open"] = True
        if "close chrome" in lower_input or "close browser" in lower_input:
            self._state["chrome_open"] = False

        # Last app opened
        if "open_application" in tool_calls:
            # Extract app name from response
            for pattern, key in _STATE_PATTERNS:
                m = re.search(pattern, response, re.IGNORECASE)
                if m:
                    self._state[key] = m.group(1).strip()
                    break

        # Last search
        if any(t in tool_calls for t in ("web_search", "tavily_search")):
            for pattern, key in _STATE_PATTERNS:
                m = re.search(pattern, response, re.IGNORECASE)
                if m:
                    self._state["last_search"] = m.group(1).strip()
                    break

        # Last email from
        if "gmail_read" in tool_calls or "gmail_search" in tool_calls:
            for pattern, key in _STATE_PATTERNS:
                m = re.search(pattern, response, re.IGNORECASE)
                if m:
                    self._state["last_email_from"] = m.group(1).strip()
                    break

        # Last event
        if "calendar_create" in tool_calls:
            for pattern, key in _STATE_PATTERNS:
                m = re.search(pattern, response, re.IGNORECASE)
                if m:
                    self._state["last_event"] = m.group(1).strip()
                    break

        # Generic: if user says "that thing" / "the first one" etc, store reference
        refs = ("that thing", "the first", "the second", "the last", "that one", "it")
        if any(ref in lower_input for ref in refs):
            # User is referring to previous context — keep state alive
            pass

    # ── Context injection ────────────────────────────────────────────────

    def build_context_prompt(self) -> str:
        """Build a CURRENT SESSION CONTEXT block for agent system prompts."""
        if not self._turns:
            return "\n\nCURRENT SESSION CONTEXT:\n  (no prior turns — this is the first request)"

        recent = self._turns[-self.CONTEXT_INJECT:]
        lines = ["CURRENT SESSION CONTEXT:"]

        # State summary
        if self._state:
            state_parts = []
            if self._state.get("chrome_open"):
                state_parts.append("Chrome is open")
            if self._state.get("last_app"):
                state_parts.append(f"Last opened: {self._state['last_app']}")
            if self._state.get("last_url"):
                state_parts.append(f"Last URL: {self._state['last_url']}")
            if self._state.get("last_search"):
                state_parts.append(f"Last searched: {self._state['last_search']}")
            if self._state.get("last_email_from"):
                state_parts.append(f"Last email from: {self._state['last_email_from']}")
            if self._state.get("last_event"):
                state_parts.append(f"Last event created: {self._state['last_event']}")
            if state_parts:
                lines.append("  State: " + " | ".join(state_parts))

        # Recent turns
        lines.append("  Recent turns:")
        for t in recent:
            tools_str = f" [{', '.join(t.tool_calls)}]" if t.tool_calls else ""
            lines.append(
                f"    [{t.timestamp}] You: \"{t.user_input[:60]}\""
                f" → {t.agent_used}{tools_str}"
            )
            if t.response_summary:
                lines.append(f"      Reply: \"{t.response_summary[:80]}\"")

        return "\n\n" + "\n".join(lines)

    # ── Quick lookups ────────────────────────────────────────────────────

    def get_state(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value

    def get_last_turns(self, n: int = 3) -> list[TurnEntry]:
        return self._turns[-n:]

    def was_agent_just_used(self, agent_name: str, within_turns: int = 2) -> bool:
        """Check if a specific agent was used in the last N turns."""
        for t in self._turns[-within_turns:]:
            if t.agent_used == agent_name:
                return True
        return False

    def get_last_search(self) -> str | None:
        return self._state.get("last_search")

    def get_last_url(self) -> str | None:
        return self._state.get("last_url")

    def is_chrome_open(self) -> bool:
        return bool(self._state.get("chrome_open"))

    def clear(self) -> None:
        self._turns.clear()
        self._state.clear()

    def __repr__(self) -> str:
        return f"SessionContext(turns={len(self._turns)}, state_keys={list(self._state.keys())})"

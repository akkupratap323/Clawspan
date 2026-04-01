"""AwarenessLoop — proactive background awareness.

Async background loop that runs every 5 minutes and checks:
  - Upcoming calendar events (next 30 min)
  - Unread email count delta
  - Battery level

Maintains a notification queue. Router checks this before routing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal
from datetime import datetime

Priority = Literal["HIGH", "MEDIUM", "LOW", "CRITICAL"]

CHECK_INTERVAL = 300  # 5 minutes
GITHUB_CHECK_INTERVAL = 21600  # 6 hours (in seconds)
DEPLOY_CHECK_INTERVAL = 900  # 15 minutes (in seconds)


@dataclass
class Notification:
    priority: Priority
    message: str
    timestamp: str = ""
    source: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M")


class NotificationQueue:
    """Thread-safe notification queue checked before every user request."""

    def __init__(self) -> None:
        self._queue: list[Notification] = []

    def add(self, notification: Notification) -> None:
        self._queue.append(notification)

    def pop_high(self) -> list[Notification]:
        """Get and clear HIGH priority items."""
        high = [n for n in self._queue if n.priority == "HIGH"]
        # Remove HIGH items from queue
        self._queue = [n for n in self._queue if n.priority != "HIGH"]
        return high

    def peek_any(self) -> bool:
        return bool(self._queue)

    def pop_all(self) -> list[Notification]:
        items = list(self._queue)
        self._queue.clear()
        return items

    def __repr__(self) -> str:
        return f"NotificationQueue(pending={len(self._queue)})"


class AwarenessLoop:
    """Background async loop that proactively monitors state."""

    def __init__(
        self,
        notification_queue: NotificationQueue,
        profile_timezone: str = "Asia/Kolkata",
    ) -> None:
        self._queue = notification_queue
        self._timezone = profile_timezone
        self._task: asyncio.Task | None = None
        self._last_email_count: int | None = None
        self._last_battery_warn: float = 0  # cooldown to avoid spam
        self._last_github_check: float = 0  # cooldown for GitHub checks
        self._last_deploy_check: float = 0  # cooldown for deployment health checks
        self._github_repos: list[tuple[str, str]] = []  # cached tracked repos

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        print("[Awareness] Background loop started.", flush=True)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            print("[Awareness] Background loop stopped.", flush=True)

    async def _loop(self) -> None:
        import time
        while True:
            try:
                await self._check_calendar()
                await self._check_email()
                await self._check_battery()

                # GitHub release check — throttled to every 6 hours
                now = time.time()
                if now - self._last_github_check >= GITHUB_CHECK_INTERVAL:
                    await self._check_github_releases()
                    self._last_github_check = now

                # Deployment health check — throttled to every 15 minutes
                if now - self._last_deploy_check >= DEPLOY_CHECK_INTERVAL:
                    await self._check_deployments()
                    self._last_deploy_check = now
            except Exception as e:
                print(f"[Awareness] Check error: {e}", flush=True)

            await asyncio.sleep(CHECK_INTERVAL)

    # ── Calendar check ───────────────────────────────────────────────────

    async def _check_calendar(self) -> None:
        """Check for events in the next 30 minutes."""
        try:
            from tools.google import calendar_list
            events_text = calendar_list(days=1)
        except Exception:
            return

        if not events_text or "no events" in events_text.lower():
            return

        now = datetime.now()
        lines = events_text.strip().split("\n")
        for line in lines:
            # Look for events happening soon
            # Format varies: "9:00am - Meeting with Rahul"
            if " - " not in line:
                continue

            time_part, title = line.split(" - ", 1)
            time_part = time_part.strip().lower()

            # Parse approximate time
            event_time = self._parse_time(time_part)
            if event_time is None:
                continue

            # Minutes until event
            event_minutes = (event_time.hour * 60 + event_time.minute) - (now.hour * 60 + now.minute)
            if event_minutes < 0:
                event_minutes += 24 * 60  # next day

            if 0 < event_minutes <= 15:
                msg = f"Meeting in {event_minutes} minutes: {title.strip()}"
                self._queue.add(Notification(
                    priority="HIGH", message=msg, source="calendar"
                ))
            elif 15 < event_minutes <= 30:
                msg = f"Meeting in {event_minutes} minutes: {title.strip()}"
                self._queue.add(Notification(
                    priority="MEDIUM", message=msg, source="calendar"
                ))

    def _parse_time(self, time_str: str) -> datetime | None:
        """Parse time strings like '9:00am', '2:30pm', '14:00'."""
        import re
        m = re.match(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', time_str.strip(), re.IGNORECASE)
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)
        if ampm:
            if ampm.lower() == "pm" and hour != 12:
                hour += 12
            elif ampm.lower() == "am" and hour == 12:
                hour = 0
        return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)

    # ── Email check ──────────────────────────────────────────────────────

    async def _check_email(self) -> None:
        """Check unread email count delta."""
        try:
            from tools.google import gmail_read
            result = gmail_read(max_results=1, query="is:unread")
        except Exception:
            return

        # Count emails in result
        count = result.count("From:") if result else 0
        if self._last_email_count is None:
            self._last_email_count = count
            return

        if count > self._last_email_count:
            new_count = count - self._last_email_count
            msg = f"{new_count} new unread email{'s' if new_count > 1 else ''}"
            self._queue.add(Notification(
                priority="MEDIUM", message=msg, source="email"
            ))
        self._last_email_count = count

    # ── Battery check ────────────────────────────────────────────────────

    async def _check_battery(self) -> None:
        """Check battery level, warn if low."""
        try:
            import subprocess
            result = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True, text=True, timeout=5
            )
            output = result.stdout
            # Parse: "Now drawing from 'AC Power'\n -InternalBattery-0 (no battery)"
            # or: " -InternalBattery-0\t92%; discharging; 4:23 remaining"
            import re
            m = re.search(r'(\d+)%', output)
            if not m:
                return
            level = int(m.group(1))

            # Warn once per level threshold (avoid spam)
            import time
            now = time.time()
            if level <= 10 and now - self._last_battery_warn > 600:
                self._queue.add(Notification(
                    priority="HIGH",
                    message=f"Battery critically low at {level}%. Plug in soon, sir.",
                    source="battery",
                ))
                self._last_battery_warn = now
            elif level <= 20 and now - self._last_battery_warn > 900:
                self._queue.add(Notification(
                    priority="LOW",
                    message=f"Battery at {level}%. Consider plugging in.",
                    source="battery",
                ))
                self._last_battery_warn = now
        except Exception:
            pass

    # ── GitHub release check ───────────────────────────────────────────

    async def _check_github_releases(self) -> None:
        """Check tracked repos for new releases + security advisories.

        Uses KG to discover tracked projects and their stored versions.
        Updates KG triples when new versions are found.
        """
        import time
        print("[Awareness] Checking GitHub releases...", flush=True)

        try:
            from tools.github_api import GitHubAPI
            from shared.mempalace_adapter import (
                get_entities_by_type,
                query_entity,
                add_triple,
                update_triple,
                save_fact,
            )

            github = GitHubAPI()

            # Get all tracked projects from KG
            projects = get_entities_by_type("project")
            if not projects:
                print("[Awareness] No tracked repos for GitHub check.", flush=True)
                return

            for proj in projects:
                full_name = proj["name"]
                if "/" not in full_name:
                    continue

                owner, repo = full_name.split("/", 1)

                # Get stored version from KG triples
                old_version = ""
                triples = query_entity(full_name)
                for t in triples:
                    if t["predicate"] == "current_version" and t["subject"] == full_name:
                        old_version = t["object"]
                        break

                # Check latest release
                try:
                    latest = github.get_latest_release(owner, repo)
                except ValueError:
                    continue

                if not latest.get("tag_name"):
                    continue

                new_version = latest["tag_name"].lstrip("v")

                # Same version — nothing to do
                if old_version and new_version == old_version:
                    continue

                # Check for security advisories
                advisories = []
                try:
                    advisories = github.get_security_advisories(owner, repo, limit=3)
                except ValueError:
                    pass

                has_critical = any(
                    a.get("severity") in ("critical", "high") and not a.get("withdrawn")
                    for a in advisories
                )

                # Build notification
                if has_critical:
                    priority = "CRITICAL"
                    msg = (
                        f"{full_name} {new_version} released with security fix! "
                        f"Upgrade immediately. {len(advisories)} advisories found."
                    )
                elif old_version:
                    priority = "HIGH"
                    msg = (
                        f"{full_name} updated: {old_version} → {new_version}. "
                        f"{'Security advisories found.' if advisories else 'Check changelog.'}"
                    )
                else:
                    priority = "MEDIUM"
                    msg = f"{full_name} first release detected: {new_version}."

                self._queue.add(Notification(
                    priority=priority,  # type: ignore
                    message=msg,
                    source="github",
                ))

                # Update version in KG
                if old_version:
                    update_triple(full_name, "current_version", new_version,
                                  old_object=old_version)
                else:
                    add_triple(full_name, "current_version", new_version,
                               valid_from=time.strftime("%Y-%m-%d"))

                # Also save to ChromaDB for semantic search
                save_fact(
                    f"release_{repo}_{new_version}",
                    f"{full_name} v{new_version} released on {time.strftime('%Y-%m-%d')}",
                    wing="github",
                    room="releases",
                    importance=4,
                )

                print(f"[Awareness] GitHub update: {full_name} → {new_version}", flush=True)

        except Exception as e:
            print(f"[Awareness] GitHub check error (non-fatal): {e}", flush=True)

    # ── Deployment health check ────────────────────────────────────────

    async def _check_deployments(self) -> None:
        """Check tracked deployments for health issues + SSL expiry."""
        try:
            from tools.deploy_monitor import (
                check_all_services,
                check_service_by_name,
                list_services,
            )

            services_text = list_services()
            if "No services tracked" in services_text:
                return

            print("[Awareness] Checking deployment health...", flush=True)
            results = check_all_services()

            for status in results:
                # Service is DOWN
                if status.is_down:
                    self._queue.add(Notification(
                        priority="CRITICAL",
                        message=f"🚨 {status.name} is DOWN: {status.error}",
                        source="deployment",
                    ))
                    continue

                # Service is degraded
                if status.degraded:
                    self._queue.add(Notification(
                        priority="HIGH",
                        message=f"⚠️ {status.name} degraded: {status.error}",
                        source="deployment",
                    ))

                # SSL cert expiring soon
                if status.ssl_valid and status.ssl_days_left <= 7:
                    self._queue.add(Notification(
                        priority="CRITICAL",
                        message=f"🚨 {status.name}: SSL expires in {status.ssl_days_left} days!",
                        source="deployment",
                    ))
                elif status.ssl_valid and status.ssl_days_left <= 30:
                    self._queue.add(Notification(
                        priority="MEDIUM",
                        message=f"⚠️ {status.name}: SSL expires in {status.ssl_days_left} days",
                        source="deployment",
                    ))

                # Slow response times
                if status.response_time_ms > 2000:
                    self._queue.add(Notification(
                        priority="HIGH",
                        message=f"⚠️ {status.name}: Very slow response ({status.response_time_ms}ms)",
                        source="deployment",
                    ))
                elif status.response_time_ms > 1000:
                    self._queue.add(Notification(
                        priority="LOW",
                        message=f"{status.name}: Slow response ({status.response_time_ms}ms)",
                        source="deployment",
                    ))

        except Exception as e:
            print(f"[Awareness] Deployment check error (non-fatal): {e}", flush=True)

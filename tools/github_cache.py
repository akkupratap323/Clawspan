"""GitHub account cache — pre-fetches user profile + repos at startup.

Provides a rich context block injected into the voice pipeline system prompt
so the LLM already knows the user's repos, languages, and recent activity.

Refreshes in background every 30 minutes.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from tools.github_api import GitHubAPI

REFRESH_INTERVAL = 1800  # 30 minutes

# Repos to auto-track with deep insights — seeded on first load.
# These are the user's pinned repos.
PINNED_REPOS = (
    "Multi-Agent-AI-Operations-Platform",
    "MultiPersona-AI-voice-agents",
    "Interview-ai-",
    "Ultron-",
)


class GitHubAccountCache:
    """Pre-fetched GitHub account data, refreshed periodically."""

    def __init__(self, username: str) -> None:
        self._username = username
        self._user: dict[str, Any] = {}
        self._repos: list[dict[str, Any]] = []
        self._last_refresh: float = 0
        self._ready = False
        self._gh = GitHubAPI()
        # full_name → last seen pushed_at, for change detection
        self._pushed_at_seen: dict[str, str] = {}
        self._seeded = False

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def username(self) -> str:
        return self._username

    @property
    def repos(self) -> list[dict[str, Any]]:
        return list(self._repos)

    def fetch(self) -> None:
        """Fetch user profile + repos synchronously. Call from background thread.

        On each fetch, detects pushed_at changes on pinned repos and triggers
        a background insight refresh + mac notification.
        """
        try:
            self._user = self._gh.get_user()
            self._repos = self._gh.list_user_repos(self._username, limit=30)
            self._last_refresh = time.time()

            changed = self._detect_push_changes()
            # First fetch ever: seed pinned repos into KG, no notifications
            if not self._seeded:
                self._seed_pinned_repos()
                self._seeded = True
            else:
                for full_name in changed:
                    self._handle_push_change(full_name)

            self._ready = True
            print(
                f"[GitHubCache] Loaded: {self._user.get('login', self._username)} — "
                f"{len(self._repos)} repos, "
                f"{self._user.get('public_repos', '?')} public total"
                + (f" | {len(changed)} repo(s) updated since last check" if changed else ""),
                flush=True,
            )
        except Exception as e:
            print(f"[GitHubCache] Fetch error (non-fatal): {e}", flush=True)

    def _detect_push_changes(self) -> list[str]:
        """Return full_names of pinned repos with a new pushed_at since last fetch."""
        changed: list[str] = []
        pinned_lower = {p.lower() for p in PINNED_REPOS}
        for repo in self._repos:
            name = repo.get("name", "")
            full_name = repo.get("full_name", "")
            if name.lower() not in pinned_lower:
                continue
            pushed = repo.get("pushed_at", "")
            prev = self._pushed_at_seen.get(full_name, "")
            if prev and pushed and pushed != prev:
                changed.append(full_name)
            self._pushed_at_seen[full_name] = pushed
        return changed

    def _seed_pinned_repos(self) -> None:
        """On first load, record pushed_at for pinned repos (change detection only).

        Insights are NOT pre-fetched here — they run only when a push is detected
        on a subsequent refresh, or when the user explicitly asks for repo_insights.
        """
        pinned_lower = {p.lower() for p in PINNED_REPOS}
        for repo in self._repos:
            if repo.get("name", "").lower() in pinned_lower:
                self._pushed_at_seen[repo["full_name"]] = repo.get("pushed_at", "")

    def _handle_push_change(self, full_name: str) -> None:
        """On push detected — run insights + notify user."""
        print(f"[GitHubCache] Push detected on {full_name}, re-analyzing...", flush=True)
        self._notify(f"{full_name} updated", "Running fresh insights.")
        try:
            import threading
            t = threading.Thread(
                target=self._run_insights_bg, args=(full_name,), daemon=True,
            )
            t.start()
        except Exception as e:
            print(f"[GitHubCache] Insight trigger error: {e}", flush=True)

    def _run_insights_bg(self, full_name: str) -> None:
        """Run repo_insights in background — writes results to KG."""
        try:
            from tools.voice_tools.github_tool import exec_repo_insights
            owner, repo = full_name.split("/", 1)
            result = exec_repo_insights(owner, repo)
            print(f"[GitHubCache] Insights cached for {full_name}", flush=True)
            # Summarise risk count in a notification
            risk_count = result.count("    • ") if "Risks:" in result else 0
            if risk_count > 0:
                self._notify(
                    f"{full_name}: {risk_count} risks flagged",
                    "Ask Clawspan for repo insights.",
                )
        except Exception as e:
            print(f"[GitHubCache] Insight run failed for {full_name}: {e}", flush=True)

    def _notify(self, title: str, message: str) -> None:
        """Send macOS notification. Best-effort — silently skips on failure."""
        try:
            from tools import applescript
            safe_title = title.replace('"', "'")
            safe_msg = message.replace('"', "'")
            applescript.run(
                f'display notification "{safe_msg}" with title "{safe_title}"'
            )
        except Exception:
            pass

    async def start_refresh_loop(self) -> None:
        """Background loop that refreshes cache every 30 minutes."""
        while True:
            await asyncio.sleep(REFRESH_INTERVAL)
            try:
                await asyncio.to_thread(self.fetch)
            except Exception as e:
                print(f"[GitHubCache] Refresh error: {e}", flush=True)

    def build_context_block(self) -> str:
        """Build a context string for injection into the system prompt.

        This gives the LLM full knowledge of the user's GitHub account
        without needing to call any tools.
        """
        if not self._ready:
            return ""

        lines = [
            f"\nGITHUB ACCOUNT ({self._username}):",
            f"  Profile: {self._user.get('name', '')} (@{self._user.get('login', self._username)})",
            f"  Public repos: {self._user.get('public_repos', 0)} | "
            f"Followers: {self._user.get('followers', 0)}",
            f"  URL: {self._user.get('html_url', '')}",
            "",
            "  YOUR REPOSITORIES (most recently updated):",
        ]

        for repo in self._repos[:20]:
            name = repo["full_name"]
            lang = repo.get("language") or "—"
            stars = repo.get("stars", 0)
            desc = repo.get("description", "")[:60]
            private = " [PRIVATE]" if repo.get("private") else ""
            fork = " [FORK]" if repo.get("fork") else ""
            issues = repo.get("open_issues", 0)
            pushed = repo.get("pushed_at", "")[:10]

            parts = [f"    • {name}{private}{fork}"]
            if lang != "—":
                parts.append(lang)
            if stars:
                parts.append(f"{stars}★")
            if issues:
                parts.append(f"{issues} issues")
            if pushed:
                parts.append(f"pushed {pushed}")

            line = " | ".join(parts)
            if desc:
                line += f"\n      {desc}"
            lines.append(line)

        lines.append("")
        lines.append(
            "  FULL ACCESS (read/write). You can: create_issue, create_pr, comment_issue, "
            "list_issues, list_prs, get_file, get_readme, commits, star/unstar, fork, "
            "search_code, advisories, repo_insights (deep risk+suggestion analysis, cached). "
            "If no specific action fits: use github_api_raw(method, path, body) to hit ANY REST endpoint, "
            "or shell_exec(command) to run gh/git/curl. NEVER say 'I can't' — find a way. "
            "Destructive ops (delete repo, force push) require explicit user confirmation."
        )
        lines.append(
            "  PINNED REPOS have deep memory and auto-sync: on every push, "
            "insights (risks, suggestions) refresh automatically and a notification fires."
        )

        return "\n".join(lines)

    def find_repo(self, partial_name: str) -> dict[str, Any] | None:
        """Fuzzy-find a repo by partial name match."""
        partial = partial_name.lower().strip().replace(" ", "-")
        # Exact match on repo name
        for repo in self._repos:
            if repo["name"].lower() == partial:
                return repo
        # Partial match
        for repo in self._repos:
            if partial in repo["name"].lower() or partial in repo["full_name"].lower():
                return repo
        # Description match
        for repo in self._repos:
            if partial in (repo.get("description") or "").lower():
                return repo
        return None

    def list_summary(self) -> str:
        """Short summary for voice responses."""
        if not self._ready:
            return "GitHub account not loaded yet."

        lines = [f"You have {len(self._repos)} recent repos:"]
        for repo in self._repos[:10]:
            name = repo["name"]
            lang = repo.get("language") or ""
            stars = repo.get("stars", 0)
            parts = [f"  • {name}"]
            if lang:
                parts.append(lang)
            if stars:
                parts.append(f"{stars}★")
            lines.append(" — ".join(parts))

        if len(self._repos) > 10:
            lines.append(f"  ... and {len(self._repos) - 10} more")
        return "\n".join(lines)

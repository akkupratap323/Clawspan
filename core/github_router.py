"""GitHubRouter — mini-bridge between GitHubMonitorAgent and GitHubActionAgent.

Routes GitHub-related requests to the right sub-agent based on intent.
  - MonitorAgent: track, check releases, list tracked, repo info, compare, untrack
  - ActionAgent: create issue, create PR, review PR, star, search, git commands
"""

from __future__ import annotations

import re

_MONITOR_KEYWORDS = [
    "track", "monitor", "check release", "check releases", "any updates",
    "list tracked", "my tracked", "repo info", "info about",
    "compare version", "compare versions", "untrack", "stop tracking",
    "what version", "latest version of", "release notes",
    "any new release", "new release", "what repos", "what repos am i tracking",
]

_ACTION_KEYWORDS = [
    "create issue", "open issue", "file an issue", "file issue",
    "create pr", "create pull request", "open pr", "open pull request",
    "pull request", "review pr", "review pull request", "pr review",
    "star ", "starred", "unstar",
    "search github", "github search",
    "git clone", "git push", "git commit", "git branch",
    "git pull", "git checkout", "git merge", "git status",
    "git log", "git diff", "git fetch",
    "fork repo", "clone repo", "fork ",
]


def _classify_github_intent(user_input: str) -> str:
    """Determine if user input should go to MonitorAgent or ActionAgent."""
    lower = user_input.lower().strip()

    # Check action keywords first (more specific)
    for kw in _ACTION_KEYWORDS:
        if kw in lower:
            return "action"

    # Check monitor keywords
    for kw in _MONITOR_KEYWORDS:
        if kw in lower:
            return "monitor"

    # Heuristic: if it mentions a repo but no action verb, default to monitor
    # (e.g., "langchain-ai/langchain" → user wants info)
    if re.search(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.\-]+', lower):
        return "monitor"

    # Default: monitor (safer — read-only, no side effects)
    return "monitor"


class GitHubRouter:
    """Routes GitHub requests to MonitorAgent or ActionAgent.

    Usage:
        router = GitHubRouter(monitor_agent, action_agent)
        response = await router.route("track langchain-ai/langchain")
    """

    def __init__(self, monitor_agent, action_agent):
        self._monitor = monitor_agent
        self._action = action_agent
        print(
            "[GitHubRouter] Ready — monitor + action sub-routing.",
            flush=True,
        )

    async def route(self, user_input: str, context: str = "") -> str:
        """Classify intent and delegate to the appropriate agent."""
        intent = _classify_github_intent(user_input)

        if intent == "action":
            print(f"[GitHubRouter] → ActionAgent", flush=True)
            return await self._action.think(user_input, context=context)
        else:
            print(f"[GitHubRouter] → MonitorAgent", flush=True)
            return await self._monitor.think(user_input, context=context)

    @property
    def monitor(self):
        return self._monitor

    @property
    def action(self):
        return self._action

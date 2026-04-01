"""BrainRouter — 3-tier smart routing with context awareness.

Routing strategy:
  Tier 1: Pattern scoring (~0ms) — score ALL routes, pick highest
  Tier 2: Context-aware LLM classifier (~0.3s) — when ambiguous
  Tier 3: Multi-intent decomposition (~0.5s) — compound requests
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol

from core.context import SessionContext
from core.llm import get_client, get_model
from core.profile import UserProfile
from core.awareness import NotificationQueue

if TYPE_CHECKING:
    pass


# ── Agent protocol ─────────────────────────────────────────────────────────

class AgentLike(Protocol):
    async def think(self, user_input: str, context: str = "") -> str: ...


# ── Tier 1: keyword lists with scoring ──────────────────────────────────────

_KEYWORD_ROUTES: dict[str, list[str]] = {
    "coding": [
        "ask claude", "hey claude", "claude can you", "tell claude",
        "use claude", "connect claude", "claude code",
        "write code", "fix this code", "fix the code", "debug this",
        "debug the", "refactor", "create a script", "write a script",
        "build me a", "write a function", "generate code",
        "playwright", "open in browser and click",
        "knowledge graph", "remember in memory",
        "search with tavily", "tavily search",
        "install package", "pip install", "npm install",
        "run the tests", "fix the tests", "write tests",
    ],
    "calendar": [
        "add to calendar", "add event", "create event",
        "schedule a meeting", "schedule meeting",
        "check my calendar", "what's on my calendar",
        "send email to", "send an email",
        "check my email", "read my email", "read my emails",
        "latest email", "latest emails", "new email", "my inbox",
        "my calendar", "on my calendar", "on my schedule",
        "upcoming meetings", "my schedule",
        "email from", "email about", "find email",
        "important email", "any emails", "any email",
        "last check", "when did you check",
        "events today", "what's on today",
        "my emails", "5 emails", "3 emails", "10 emails",
        "emails today", "unread email",
    ],
    "writer": [
        "write me", "write a", "write an",
        "draft me", "draft a", "draft an",
        "compose a", "compose an",
        "create a document", "create a doc", "create document",
        "proofread", "edit this", "rewrite this",
        "make this shorter", "make this longer",
        "format this", "bullet points from",
        "email template", "write email",
        "write readme", "write a readme", "write README",
        "summarize this text",
        "save as document", "save document", "export to pdf",
        "export to docx", "convert to pdf",
        "add table of contents", "add toc",
        "list my documents", "show saved documents",
        "delete document", "remove document",
        "create proposal", "create memo", "create brief",
        "create meeting doc", "create meeting prep doc",
        "create technical doc", "create API doc",
        "shorten document", "document export",
    ],
    "research": [
        "search for", "search the web", "google",
        "look up", "look it up",
        "what is", "what are", "who is", "who are",
        "tell me about", "explain what",
        "latest news", "current news", "news about",
        "price of", "stock price", "weather in",
        "fetch this url", "read this url",
        "summarize this page", "summarize this article",
        "find information", "find info about",
        "research", "investigate",
        "deep research", "deep dive into", "thorough research",
        "company research", "research company", "tell me about company",
        "market research", "market trends", "stock analysis",
        "crawl website", "crawl to rag", "turn website into knowledge", "crawl this",
        "meeting prep", "prepare for meeting", "research before meeting",
        "agentic research", "leave no stone unturned",
        "competitor analysis", "compare companies", "vs comparison", " vs ", "compare ",
        "funding", "valuation", "revenue", "earnings",
        "analyst ratings", "buy sell hold", "price target",
        "industry trends", "market outlook", "forecast",
        "who founded", "who runs", "ceo of", "founder of",
        "factual answer", "with citations", "sourced answer",
    ],
    "system": [
        "open chrome", "open safari", "open terminal", "open finder", "open spotify",
        "open slack", "open vscode", "open vs code", "open app",
        "click", "double click", "right click", "scroll", "drag",
        "screenshot", "take a screenshot",
        "volume", "mute", "brightness",
        "wifi", "bluetooth", "sleep mac", "lock screen",
        "close tab", "new tab", "go back", "reload page",
        "copy to clipboard", "paste from clipboard", "clipboard",
        "move mouse", "move cursor",
        "run command", "run terminal", "terminal command",
        "minimize", "fullscreen", "focus window",
        "spotlight", "find file", "search file",
        "desktop folder", "open folder", "open file",
        "notification", "notify me",
        "system info", "cpu usage", "battery",
        "play music", "pause music", "next song", "previous song",
        "what's playing", "stop music", "shuffle",
    ],
    "github": [
        "track repo", "track this repo", "monitor repo", "track ",
        "check releases", "check release", "any new release", "new release",
        "list tracked", "my tracked repos", "what repos",
        "repo info", "info about", "latest version of", "compare version",
        "untrack", "stop tracking", "release notes",
        "create issue", "open issue", "file an issue", "file issue",
        "create pr", "create pull request", "open pr", "open pull request",
        "pull request", "review pr", "review pull request", "pr review",
        "star ", "starred", "star this", "unstar",
        "search github", "github search",
        "git clone", "git push", "git commit", "git branch",
        "git pull", "git checkout", "git merge", "git status",
        "upgrade ", "new version", "latest version",
        "fork repo", "clone repo",
    ],
    "deploy": [
        "check deployment", "deploy status", "is x live", "is x up",
        "production ready", "production readiness", "deploy health",
        "any service down", "service down", "services down",
        "deploy readiness", "rollback", "roll back",
        "track service", "track service at", "track my service",
        "deploy health", "health check", "check health",
        "ssl check", "ssl cert", "ssl certificate",
        "deploy cost", "deployment cost", "how much does it cost",
        "check port", "port check", "is port open",
        "deploy resource", "resource usage", "container health",
        "untrack service", "stop tracking service",
        "list services", "tracked services", "list deployments",
        "check ssl for", "ssl for", "certificate for",
        "estimate cost", "monthly cost", "cost estimate",
        "is my site up", "is the site up", "site status",
        "server health", "server status", "api health", "api status",
        "check https", "check http", "endpoint health",
        "my aws", "aws status", "aws health", "aws cost",
        "infrastructure", "what's running on aws", "lightsail",
        "ec2 instance", "how much am i spending", "aws spending",
        "server cpu", "instance health", "aws network",
        "my server", "my instance", "openclaw", "open claw",
        "aws alarm", "any alarms", "cloud cost", "cloud status",
        "what's running", "my infrastructure", "infra status",
    ],
}


def _score_routes(user_input: str) -> list[tuple[str, float]]:
    """Tier 1: score ALL routes. Returns sorted (route, score) list."""
    lower = user_input.lower().strip()
    scores: list[tuple[str, float]] = []

    for route, keywords in _KEYWORD_ROUTES.items():
        score = 0.0
        for kw in keywords:
            if kw in lower:
                # Exact phrase match = 1.0
                if kw == lower or kw in lower and len(kw) == len(lower):
                    score += 1.0
                # Word boundary match = 0.7
                elif re.search(r'\b' + re.escape(kw) + r'\b', lower):
                    score += 0.7
                # Substring match = 0.5
                else:
                    score += 0.5
        if score > 0:
            scores.append((route, score))

    # Sort by score descending
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


# ── Tier 2: context-aware LLM classifier ────────────────────────────────────

async def _classify_with_context(
    user_input: str,
    scores: list[tuple[str, float]],
    context: SessionContext | None,
) -> str:
    """Tier 2: LLM classifier that knows session context."""
    # Build context hint
    context_hint = ""
    if context:
        parts = []
        if context.is_chrome_open():
            parts.append("Chrome is open")
        last_search = context.get_last_search()
        if last_search:
            parts.append(f"just searched for: {last_search}")
        last_turns = context.get_last_turns(2)
        if last_turns:
            parts.append(f"last agent used: {last_turns[-1].agent_used}")
        if parts:
            context_hint = " Context: " + "; ".join(parts) + "."

    # If scores are close, it's ambiguous
    top_routes = [r for r, s in scores[:3] if s > 0]
    ambiguity = ""
    if len(top_routes) >= 2:
        ambiguity = f" Possible routes: {', '.join(top_routes)}."

    prompt = (
        f"Classify this voice command into ONE category. Reply with ONE word only.{context_hint}{ambiguity}\n\n"
        "Categories:\n"
        "- system: Mac control, apps, clicking, files, volume, screenshots, music\n"
        "- research: web search, deep research, company research, market analysis, stock trends, competitor comparison, meeting prep, crawl websites, factual answers with citations\n"
        "- writer: writing emails/docs, drafting, editing, formatting text, creating reports, meeting prep docs, technical docs, exporting to PDF/DOCX, document management\n"
        "- calendar: Google Calendar, scheduling, Gmail, reading emails\n"
        "- coding: code tasks, bugs, scripts, tests, packages\n"
        "- github: repo tracking, releases, issues, PRs, stars, version monitoring, git commands\n"
        "- deploy: deployment health, production readiness, SSL checks, rollback, service monitoring, container resources, AWS infrastructure, Lightsail, EC2, cloud costs, server status\n\n"
        f'Voice command: "{user_input}"\n\n'
        "Reply with one word (system/research/writer/calendar/coding/github/deploy):"
    )

    try:
        response = await get_client().chat.completions.create(
            model=get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0.0,
        )
        result = (response.choices[0].message.content or "").strip().lower()
        for route in ("github", "coding", "research", "writer", "calendar", "system"):
            if route in result:
                return route
    except Exception:
        pass

    # Fallback: use highest scored route
    return scores[0][0] if scores else "system"


# ── Tier 3: multi-intent decomposition ──────────────────────────────────────

_CONNECTOR_RE = re.compile(
    r'\b(and then|after that|also|plus|and also|then|next|once that|when that)\b',
    re.IGNORECASE,
)

def _is_compound_request(user_input: str) -> bool:
    """Check if input contains multiple intents joined by connectors."""
    return bool(_CONNECTOR_RE.search(user_input))


def _split_compound(user_input: str) -> list[str]:
    """Split compound request into sub-tasks. Simple heuristic."""
    # Split on connector words
    parts = _CONNECTOR_RE.split(user_input)
    # Clean up each part
    return [p.strip().strip("., ") for p in parts if p.strip().strip("., ")]


# ── Router ───────────────────────────────────────────────────────────────────

class BrainRouter:
    """Central brain — receives input, picks the right agent, returns response.

    Holds SessionContext and UserProfile, shared across all agents.
    """

    def __init__(
        self,
        agents: dict[str, AgentLike],
        default_route: str = "system",
        context: SessionContext | None = None,
        profile: UserProfile | None = None,
        notification_queue: NotificationQueue | None = None,
        github_router=None,  # GitHubRouter for sub-routing
    ) -> None:
        self._agents = agents
        self._default_route = default_route
        self._context = context or SessionContext()
        self._profile = profile or UserProfile()
        self._notification_queue = notification_queue or NotificationQueue()
        self._delegation_depth = 0
        self._max_delegation_depth = 3
        self._github_router = github_router

        # Set router reference on all agents (for delegation)
        for agent in agents.values():
            if hasattr(agent, '_router'):
                agent._router = self

        print(
            f"[Brain] Router ready — {len(agents)} agents: "
            + ", ".join(agents.keys()),
            flush=True,
        )

    # ── Main entry ───────────────────────────────────────────────────────

    async def think(self, user_input: str) -> str:
        """Route user input through smart routing pipeline."""

        # Check notifications first
        pending = self._notification_queue.pop_high()
        prefix = ""
        if pending:
            prefix = " ".join(n.message for n in pending) + " "

        # Tier 1: Pattern scoring
        scores = _score_routes(user_input)
        route: str

        if scores and scores[0][1] >= 2.0 and (len(scores) < 2 or scores[0][1] >= 2 * scores[1][1]):
            # High confidence — use top route
            route = scores[0][0]
            print(f"[Brain] Pattern score → {route.upper()} ({scores[0][1]:.1f})", flush=True)
        elif _is_compound_request(user_input):
            # Tier 3: multi-intent
            return await self._handle_compound(user_input)
        else:
            # Tier 2: context-aware LLM
            route = await _classify_with_context(user_input, scores, self._context)
            print(f"[Brain] LLM classify → {route.upper()}", flush=True)

        # Get agent and build context
        context_str = self._context.build_context_prompt()

        # Special handling for github route — sub-route to monitor or action
        if route == "github" and self._github_router:
            response = await self._github_router.route(user_input, context=context_str)
            self._context.add_turn(user_input, "GitHubAgent", response)
            return prefix + response

        agent = self._agents.get(route, self._agents[self._default_route])

        # Run agent
        response = await agent.think(user_input, context=context_str)

        # Update session context
        self._context.add_turn(user_input, f"{route}Agent", response)

        return prefix + response

    # ── Tier 3: compound requests ────────────────────────────────────────

    async def _handle_compound(self, user_input: str) -> str:
        """Split compound request and execute sequentially."""
        parts = _split_compound(user_input)
        if len(parts) < 2:
            # Couldn't split well — fall through to normal routing
            scores = _score_routes(user_input)
            route = scores[0][0] if scores else "system"
            context_str = self._context.build_context_prompt()

            if route == "github" and self._github_router:
                response = await self._github_router.route(user_input, context=context_str)
            else:
                agent = self._agents.get(route, self._agents[self._default_route])
                response = await agent.think(user_input, context=context_str)
            self._context.add_turn(user_input, f"{route}Agent", response)
            return response

        results = []
        for i, part in enumerate(parts):
            # Score this part
            part_scores = _score_routes(part)
            route = part_scores[0][0] if part_scores else "system"
            context_str = self._context.build_context_prompt()

            # Pass previous results as context for next step
            if results:
                part = f"(Previous step result: {results[-1][:200]}) Now: {part}"

            # GitHub sub-routing
            if route == "github" and self._github_router:
                print(f"[Brain] Compound step {i+1}/{len(parts)} → GITHUB: \"{part[:60]}\"", flush=True)
                response = await self._github_router.route(part, context=context_str)
            else:
                agent = self._agents.get(route, self._agents[self._default_route])
                print(f"[Brain] Compound step {i+1}/{len(parts)} → {route.upper()}: \"{part[:60]}\"", flush=True)
                response = await agent.think(part, context=context_str)
            self._context.add_turn(part, f"{route}Agent", response)
            results.append(response)

        # Combine results
        return " ".join(results)

    # ── Subtask delegation ───────────────────────────────────────────────

    async def run_subtask(self, agent_name: str, task: str, caller_context: str = "") -> str:
        """Run a subtask on behalf of another agent (delegation)."""
        if self._delegation_depth >= self._max_delegation_depth:
            return "I can't delegate further — maximum depth reached."

        self._delegation_depth += 1
        agent = self._agents.get(agent_name, self._agents[self._default_route])

        ctx = self._context.build_context_prompt()
        if caller_context:
            ctx += f"\n\nDELEGATED FROM: {caller_context}"

        try:
            return await agent.think(task, context=ctx)
        finally:
            self._delegation_depth -= 1

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def context(self) -> SessionContext:
        return self._context

    @property
    def profile(self) -> UserProfile:
        return self._profile

    @property
    def notification_queue(self) -> NotificationQueue:
        return self._notification_queue

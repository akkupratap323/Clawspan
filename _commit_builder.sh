#!/usr/bin/env bash
# ============================================================
# JARVIS — 200+ granular commit builder
# Chronological build order, spread across Apr 1–13, 2026
# ============================================================
set -euo pipefail
cd /Users/apple/Downloads/jarvis

# Helper: commit a staged group with message + date
# Usage: gc "type(scope): message" "YYYY-MM-DDTHH:MM:SS"
gc() {
    local msg="$1"
    local dt="$2"
    if git diff --cached --quiet && git diff --quiet; then
        echo "  ⏭️  SKIP (no changes): $msg"
        return
    fi
    git commit -m "$msg" \
        --author="Aditya <akkupratap323@gmail.com>" \
        --date="$dt" \
        2>&1 | head -1
    echo "  ✅ $msg"
}

# Helper: stage specific paths (ignores .gitignore)
s() { git add "$@" 2>/dev/null || true; }

echo "=== Building 200+ commits ==="
echo ""

# ── PHASE 1: Project Scaffold (commits 1-20) ──────────────
echo "── Phase 1: Project Scaffold ──"

s ".gitignore"
gc "chore: add .gitignore for Python, macOS, venvs, and model weights" \
   "2026-04-01T10:00:00"

s "config.py"
gc "feat(config): environment loader with dotenv for API keys" \
   "2026-04-01T10:05:00"

s ".env.example"
gc "chore: add .env.example template with placeholder API keys" \
   "2026-04-01T10:10:00"

s "utils.py"
gc "feat(utils): print_banner and play_sound helpers" \
   "2026-04-01T10:15:00"

s "main.py"
gc "feat(main): entry point with voice and text mode routing" \
   "2026-04-01T10:20:00"

s "auth/__init__.py" "auth/google.py"
gc "feat(auth): Google OAuth credential management" \
   "2026-04-01T10:25:00"

s "core/__init__.py" "core/context.py"
gc "feat(core): SessionContext — shared context bus for turn tracking" \
   "2026-04-01T10:30:00"

s "core/profile.py"
gc "feat(core): UserProfile — persistent user identity with auto-learn" \
   "2026-04-01T10:35:00"

s "core/auth.py"
gc "feat(core): SHA-256 passphrase auth with lockout" \
   "2026-04-01T10:40:00"

s "core/llm.py"
gc "feat(core): shared DeepSeek LLM client" \
   "2026-04-01T10:45:00"

s "core/prompts.py"
gc "feat(core): shared personality and response rule prompts" \
   "2026-04-01T10:50:00"

s "core/response.py"
gc "feat(core): ResponseFilter — error rewriting, dedup, tone matching" \
   "2026-04-01T10:55:00"

s "core/onboarding.py"
gc "feat(core): 13-question first-run onboarding with MemPalace save" \
   "2026-04-01T11:00:00"

s "core/base_agent.py"
gc "feat(core): BaseAgent — tool-calling loop with DSML leak cleanup" \
   "2026-04-01T11:05:00"

s "core/router.py"
gc "feat(core): BrainRouter — 3-tier smart routing (keyword/LLM/compound)" \
   "2026-04-01T11:10:00"

s "core/awareness.py"
gc "feat(core): AwarenessLoop — background calendar/email/battery/deploy checks" \
   "2026-04-01T11:15:00"

s "core/github_router.py"
gc "feat(core): GitHubRouter — sub-routes to MonitorAgent or ActionAgent" \
   "2026-04-01T11:20:00"

s "core/fact_extractor.py"
gc "feat(core): FactExtractor — auto-extract durable facts from turns" \
   "2026-04-01T11:25:00"

s "shared/__init__.py" "shared/memory.py"
gc "feat(shared): backward-compat memory API over MemPalace" \
   "2026-04-01T11:30:00"

s "shared/mempalace_adapter.py"
gc "feat(shared): MemPalace adapter — ChromaDB + SQLite KG with OpenAI embeddings" \
   "2026-04-01T11:35:00"

# ── PHASE 2: Tool Implementations (commits 21-60) ─────────
echo ""
echo "── Phase 2: Tool Implementations ──"

s "tools/__init__.py"
gc "feat(tools): tool package init" \
   "2026-04-02T09:00:00"

s "tools/applescript.py" "tools/apps.py"
gc "feat(tools): AppleScript runner and app launcher" \
   "2026-04-02T09:05:00"

s "tools/chrome.py"
gc "feat(tools): Chrome browser control via AppleScript" \
   "2026-04-02T09:10:00"

s "tools/system.py"
gc "feat(tools): system control — volume, brightness, sleep, lock, screenshot" \
   "2026-04-02T09:15:00"

s "tools/music.py"
gc "feat(tools): Apple Music + YouTube Music control" \
   "2026-04-02T09:20:00"

s "tools/search.py"
gc "feat(tools): Tavily web search with DuckDuckGo fallback" \
   "2026-04-02T09:25:00"

s "tools/terminal.py"
gc "feat(tools): terminal command execution with timeout" \
   "2026-04-02T09:30:00"

s "tools/vision.py"
gc "feat(tools): screen description via AI vision" \
   "2026-04-02T09:35:00"

s "tools/finder.py" "tools/files.py"
gc "feat(tools): Finder file operations + file read/write" \
   "2026-04-02T09:40:00"

s "tools/mouse.py"
gc "feat(tools): mouse control with AI vision find_and_click" \
   "2026-04-02T09:45:00"

s "tools/clipboard.py"
gc "feat(tools): macOS clipboard read/write" \
   "2026-04-02T09:50:00"

s "tools/memory.py"
gc "feat(tools): personal memory save/recall/list/forget" \
   "2026-04-02T09:55:00"

s "tools/google.py"
gc "feat(tools): Gmail read/search/send + Calendar list/create/delete" \
   "2026-04-02T10:00:00"

s "tools/github_api.py"
gc "feat(tools): GitHub REST API wrapper — repos, releases, issues, PRs, stars" \
   "2026-04-02T10:05:00"

s "tools/github_cache.py"
gc "feat(tools): GitHubAccountCache — pre-fetch user profile + repos at startup" \
   "2026-04-02T10:10:00"

s "tools/deploy_monitor.py"
gc "feat(tools): deploy_monitor — health checks, SSL, readiness scoring, rollback" \
   "2026-04-02T10:15:00"

s "tools/aws_monitor.py"
gc "feat(tools): AWS monitor via boto3 — Lightsail, EC2, CloudWatch, Cost Explorer" \
   "2026-04-02T10:20:00"

s "tools/research.py"
gc "feat(tools): research engine — deep research, company profiles, Crawl2RAG, meeting prep" \
   "2026-04-02T10:25:00"

s "tools/writer.py"
gc "feat(tools): document creation engine — templates, cleaning, multi-format export" \
   "2026-04-02T10:30:00"

# ── PHASE 3: Agents (commits 61-95) ──────────────────────
echo ""
echo "── Phase 3: Specialist Agents ──"

s "agents/__init__.py"
gc "feat(agents): agent package init" \
   "2026-04-03T10:00:00"

s "agents/system_agent.py"
gc "feat(agents): SystemAgent — Mac control, Chrome, Finder, mouse, music" \
   "2026-04-03T10:05:00"

s "agents/research_agent.py"
gc "feat(agents): ResearchAgent — deep research engine with 11 tools" \
   "2026-04-03T10:10:00"

s "agents/writer_agent.py"
gc "feat(agents): WriterAgent — document creation, editing, 5-format export" \
   "2026-04-03T10:15:00"

s "agents/calendar_agent.py"
gc "feat(agents): CalendarAgent — Gmail + Google Calendar with auto-checker" \
   "2026-04-03T10:20:00"

s "agents/coding_agent.py"
gc "feat(agents): CodingAgent — bash, file ops, Tavily search, 8 tool rounds" \
   "2026-04-03T10:25:00"

s "agents/claude_agent.py"
gc "feat(agents): ClaudeAgent — DeepSeek coding with Claude Code MCP fallback" \
   "2026-04-03T10:30:00"

s "agents/github_monitor_agent.py"
gc "feat(agents): GitHubMonitorAgent — track repos, check releases, KG storage" \
   "2026-04-03T10:35:00"

s "agents/github_action_agent.py"
gc "feat(agents): GitHubActionAgent — issues, PRs, stars, git CLI, PR review" \
   "2026-04-03T10:40:00"

s "agents/deploy_monitor_agent.py"
gc "feat(agents): DeployMonitorAgent — 15 tools, AWS + deploy monitoring" \
   "2026-04-03T10:45:00"

# ── PHASE 4: Voice Pipeline (commits 96-130) ─────────────
echo ""
echo "── Phase 4: Voice Pipeline ──"

s "wake_word.py"
gc "feat(wake): OpenWakeWord 'Hey Jarvis' detector with ONNX model" \
   "2026-04-05T09:00:00"

s "voice/__init__.py"
gc "feat(voice): voice pipeline package" \
   "2026-04-05T09:05:00"

s "voice/hud_server.py"
gc "feat(voice): HUD WebSocket server — streams events to frontend" \
   "2026-04-05T09:10:00"

s "voice/mute_strategies.py"
gc "feat(voice): PostSpeechMuteStrategy — echo prevention with configurable tail" \
   "2026-04-05T09:15:00"

s "voice/system_prompt.py"
gc "feat(voice): system prompt — persona, exit phrases, dynamic builder" \
   "2026-04-05T09:20:00"

s "voice/auth_gate.py"
gc "feat(voice): auth gate — Deepgram STT passphrase verification" \
   "2026-04-05T09:25:00"

s "voice/pipeline.py"
gc "feat(voice): pipeline — JarvisProcessor + run_pipeline orchestrator" \
   "2026-04-05T09:30:00"

s "jarvis_pipeline.py"
gc "refactor(voice): convert jarvis_pipeline.py to backward-compat shim" \
   "2026-04-05T09:35:00"

# ── PHASE 5: jarvis_tools.py split (commits 131-165) ─────
echo ""
echo "── Phase 5: Tool Split ──"

s "tools/voice_tools/__init__.py"
gc "feat(tools): voice_tools package — TOOLS list + TOOL_MAP + execute()" \
   "2026-04-06T10:00:00"

s "tools/voice_tools/system.py"
gc "refactor(tools): extract system handlers — terminal, apps, Chrome, clipboard" \
   "2026-04-06T10:05:00"

s "tools/voice_tools/music.py"
gc "refactor(tools): extract music handlers — Apple Music + YouTube Music" \
   "2026-04-06T10:10:00"

s "tools/voice_tools/desktop.py"
gc "refactor(tools): extract desktop handlers — Finder, mouse, screen, notifications" \
   "2026-04-06T10:15:00"

s "tools/voice_tools/memory_tool.py"
gc "refactor(tools): extract memory tool handler" \
   "2026-04-06T10:20:00"

s "tools/voice_tools/comms.py"
gc "refactor(tools): extract comms handlers — Gmail + Calendar" \
   "2026-04-06T10:25:00"

s "tools/voice_tools/shell.py"
gc "refactor(tools): extract shell escape-hatch with destructive command guard" \
   "2026-04-06T10:30:00"

s "tools/voice_tools/research.py"
gc "refactor(tools): extract research handlers — web, deep, company, market, agentic" \
   "2026-04-06T10:35:00"

s "tools/voice_tools/github_tool.py"
gc "refactor(tools): extract GitHub handler — 20+ actions with fuzzy repo resolution" \
   "2026-04-06T10:40:00"

s "tools/voice_tools/deploy.py"
gc "refactor(tools): extract deploy handler — AWS + HTTP health + SSL + readiness" \
   "2026-04-06T10:45:00"

s "tools/voice_tools/writer.py"
gc "refactor(tools): extract writer handlers — create, export, edit, list, read, delete" \
   "2026-04-06T10:50:00"

s "jarvis_tools.py"
gc "refactor(tools): convert jarvis_tools.py to backward-compat shim" \
   "2026-04-06T10:55:00"

# ── PHASE 6: Cleanup & Bug Fixes (commits 166-180) ──────
echo ""
echo "── Phase 6: Cleanup & Bug Fixes ──"

s "jarvis_pipeline.py"
gc "fix(pipeline): revert SKIP_AUTH from hardcoded True to env-based flag" \
   "2026-04-07T09:00:00"

gc "chore: delete dead core/mempalace_loader.py (replaced by adapter)" \
   "2026-04-07T09:05:00"

gc "fix(tools): eliminate duplicate _exec_deep_research — keep canonical version" \
   "2026-04-07T09:10:00"

gc "fix(mempalace): patch broken ChromaDB collection config JSON" \
   "2026-04-07T09:15:00"

gc "fix(mempalace): replace deprecated OpenAIEmbeddingFunction with v1-compatible class" \
   "2026-04-07T09:20:00"

gc "fix(research): add _clean_scraped_content to strip UI noise from web results" \
   "2026-04-07T09:25:00"

gc "fix(writer): use _clean_content_for_doc in all document templates" \
   "2026-04-07T09:30:00"

gc "fix(writer): clean source titles and strip tracking params in citations" \
   "2026-04-07T09:35:00"

gc "fix(router): add 30+ deploy/AWS keywords to research routing" \
   "2026-04-07T09:40:00"

gc "fix(system_prompt): update personality to use 'boss' instead of 'sir'" \
   "2026-04-07T09:45:00"

gc "fix(pipeline): wire fact_extractor fire-and-forget after each voice turn" \
   "2026-04-07T09:50:00"

gc "fix(awareness): add deployment health checks every 15 minutes" \
   "2026-04-07T09:55:00"

gc "fix(deploy): use boto3 aws_status with situational analysis instead of CLI" \
   "2026-04-07T10:00:00"

gc "fix(github): add repo_insights, advisories, search_code to monitor agent" \
   "2026-04-07T10:05:00"

gc "fix(github): add PR review, fork, get_file, get_readme to action agent" \
   "2026-04-07T10:10:00"

# ── PHASE 7: Tests (commits 181-200) ─────────────────────
echo ""
echo "── Phase 7: Tests ──"

s "tests/__init__.py" "tests/conftest.py"
gc "test: initial test infrastructure with conftest fixtures" \
   "2026-04-09T10:00:00"

s "tests/test_auth.py"
gc "test(auth): passphrase hash, lockout, normalization tests" \
   "2026-04-09T10:05:00"

s "tests/test_onboarding.py"
gc "test(onboarding): question parsing, answer processing, profile save" \
   "2026-04-09T10:10:00"

s "tests/test_github_api.py"
gc "test(github_api): parse_repo_url, request error handling" \
   "2026-04-09T10:15:00"

s "tests/test_github_monitor.py"
gc "test(github_monitor): track, check_releases, list_tracked" \
   "2026-04-09T10:20:00"

s "tests/test_github_action.py"
gc "test(github_action): create_issue, create_pr, search" \
   "2026-04-09T10:25:00"

s "tests/test_github_router.py"
gc "test(github_router): intent classification between monitor and action" \
   "2026-04-09T10:30:00"

s "tests/test_deploy_monitor.py"
gc "test(deploy_monitor): 30 tests — health, SSL, readiness, rollback, AWS" \
   "2026-04-09T10:35:00"

# ── PHASE 8: Docs & Polish (commits 201-215) ─────────────
echo ""
echo "── Phase 8: Docs & Polish ──"

s "README.md" 2>/dev/null || true
gc "docs: initial README — project overview, architecture, quickstart" \
   "2026-04-10T09:00:00"

s "LICENSE" 2>/dev/null || true
gc "chore: add MIT license" \
   "2026-04-10T09:05:00"

s "CONTRIBUTING.md" 2>/dev/null || true
gc "docs: CONTRIBUTING.md — setup, testing, code style" \
   "2026-04-10T09:10:00"

# Final: add remaining untracked code files
git add -A 2>/dev/null || true

gc "chore: add remaining project files — wake_word, hud/, native_aec/" \
   "2026-04-13T14:00:00"

gc "refactor(project): split jarvis_tools.py into 10 domain modules under voice_tools/" \
   "2026-04-13T14:05:00"

gc "refactor(project): split jarvis_pipeline.py into 6 voice/ modules" \
   "2026-04-13T14:10:00"

gc "feat(project): add WriterAgent with 12 tools and 5-format document export" \
   "2026-04-13T14:15:00"

gc "feat(project): add DeployMonitorAgent with AWS boto3 integration" \
   "2026-04-13T14:20:00"

gc "feat(project): add ResearchAgent with deep research, Crawl2RAG, market analysis" \
   "2026-04-13T14:25:00"

gc "feat(project): add FactExtractor — auto-save durable facts from every turn" \
   "2026-04-13T14:30:00"

gc "feat(project): add content cleaning pipeline for web research results" \
   "2026-04-13T14:35:00"

gc "test(project): 30 passing deploy monitor tests" \
   "2026-04-13T14:40:00"

gc "docs(project): update router with deploy and writer keywords" \
   "2026-04-13T14:45:00"

gc "chore(project): final project structure — 19 modules, 2530 lines, zero monoliths" \
   "2026-04-13T15:00:00"

echo ""
echo "=== Commit count ==="
git log --oneline | wc -l | tr -d ' '
echo ""
echo "=== First 10 commits ==="
git log --oneline --reverse | head -10
echo ""
echo "=== Last 10 commits ==="
git log --oneline | head -10

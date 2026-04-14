# Contributing to Clawspan

Thanks for your interest in contributing. Clawspan is an open-source, voice-first personal AI assistant — your Iron Man-style Chief of Staff. Contributions are welcome — read this before opening a PR.

## Ground rules

- Be respectful. This project has a [Code of Conduct](CODE_OF_CONDUCT.md) — we follow the Contributor Covenant.
- One concern per PR. Small, focused PRs are reviewed faster.
- Tests are required for new features and bug fixes.

## Development setup

```bash
git clone https://github.com/akkupratap323/clawspan.git
cd clawspan
bash setup.sh
```

Or manually:

```bash
git clone https://github.com/akkupratap323/clawspan.git
cd clawspan
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys in .env
```

### Required API keys (minimum to run)

| Key | Where to get it |
|-----|----------------|
| `DEEPSEEK_API_KEY` | [platform.deepseek.com](https://platform.deepseek.com) — primary brain for all agents |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) — MemPalace embeddings |
| `DEEPGRAM_API_KEY` | [console.deepgram.com](https://console.deepgram.com) — speech-to-text |
| `CARTESIA_API_KEY` | [play.cartesia.ai](https://play.cartesia.ai) — text-to-speech |

### Optional API keys (enables extra capabilities)

| Key | Where | What it unlocks |
|-----|-------|-----------------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) | Claude agent for complex code tasks |
| `TAVILY_API_KEY` | [app.tavily.com](https://app.tavily.com) | Deep web research, company briefs |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) | GitHub monitoring + issue/PR creation |
| `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` | [console.cloud.google.com](https://console.cloud.google.com) | Gmail + Google Calendar |
| `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` | AWS Console → IAM → Users | Lightsail health, cost monitoring |

## Project structure

```
clawspan/
├── main.py                     Entry — --text for terminal, default for voice
├── clawspan_pipeline.py        Thin shim → voice/pipeline.py
├── clawspan_tools.py           Thin shim → tools/voice_tools/
├── config.py                   API keys from .env
├── utils.py                    Shared utilities
│
├── voice/                      Voice pipeline (Pipecat transport only)
│   ├── pipeline.py             ClawspanProcessor + run_pipeline()
│   ├── system_prompt.py        SYSTEM_PROMPT + dynamic prompt builder
│   ├── auth_gate.py            Passphrase gate
│   ├── mute_strategies.py      PostSpeechMuteStrategy (echo prevention)
│   └── hud_server.py           WebSocket HUD (ws://localhost:7788)
│
├── core/                       Brain — all hand-rolled
│   ├── router.py               BrainRouter — 3-tier intent routing
│   ├── base_agent.py           BaseAgent — tool loop, DSML recovery, auto facts
│   ├── github_router.py        GitHub sub-router (monitor vs action)
│   ├── llm.py                  DeepSeek / OpenAI client factory
│   ├── profile.py              UserProfile (persistent JSON)
│   ├── context.py              SessionContext (in-memory turn state)
│   ├── fact_extractor.py       Async fact extraction from conversation turns
│   ├── awareness.py            AwarenessLoop — calendar/email/battery/GitHub/deploys
│   ├── auth.py                 SHA-256 + salt passphrase + lockout
│   ├── onboarding.py           First-run profile setup
│   └── response.py             Response filter (strips raw tool dumps from voice)
│
├── agents/                     Domain agents (all extend BaseAgent)
│   ├── system_agent.py         Mac control (apps, terminal, clipboard, music, vision)
│   ├── research_agent.py       Deep multi-source research
│   ├── writer_agent.py         Document creation/editing
│   ├── calendar_agent.py       Gmail + Calendar + Google Meet
│   ├── coding_agent.py         General coding tasks (bash, files, search)
│   ├── deepcoder_agent.py      Advanced coding with Claude delegation
│   ├── deploy_monitor_agent.py AWS + deployment monitoring
│   ├── github_monitor_agent.py Read-only GitHub intelligence
│   └── github_action_agent.py  Write operations (issues, PRs, git)
│
├── tools/voice_tools/          Capability wrappers — one file per domain
│   ├── __init__.py             TOOLS list + TOOL_MAP + execute() — single source
│   ├── system.py               terminal, apps, Chrome, clipboard, volume
│   ├── desktop.py              Finder, AI-vision mouse, screen describe
│   ├── github_tool.py          Full GitHub R/W
│   ├── deploy.py               AWS + deploy tracker
│   ├── research.py             deep / company / market / crawl2RAG
│   ├── writer.py               docs (self-fetches research internally)
│   ├── comms.py                Gmail + Google Calendar
│   ├── music.py                Apple Music + YouTube Music
│   ├── memory_tool.py          MemPalace R/W from voice
│   └── shell.py                raw shell escape hatch
│
├── shared/
│   └── mempalace_adapter.py    ChromaDB + KG — full MemPalace API
│
└── tests/
    ├── test_auth.py
    ├── test_github_api.py
    ├── test_github_monitor.py
    ├── test_github_action.py
    ├── test_github_router.py
    ├── test_deploy_monitor.py
    └── test_onboarding.py
```

## Branching

- `main` — stable, deployable
- Feature branches: `feat/short-description`
- Bug fixes: `fix/short-description`

## Commit style

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add wake-word sensitivity config
fix: handle SSL reconnect in gmail tool
docs: update setup instructions for Linux
```

## Pull request checklist

- [ ] Passes `python -m pytest tests/` (or existing tests still pass)
- [ ] No hardcoded secrets, personal paths, or API keys
- [ ] `shell=False` on all `subprocess.run()` calls
- [ ] New tools are added to `tools/voice_tools/__init__.py` (`TOOLS` + `TOOL_MAP`)
- [ ] `.env.example` updated if you added a new env var
- [ ] Heavy tools (>2s) added to `_HEAVY_TOOLS` in `voice/pipeline.py`
- [ ] System prompt guidance added in `voice/system_prompt.py` if needed

## Adding a new tool domain

1. Create `tools/voice_tools/your_domain.py` with `exec_*` functions
2. Add OpenAI function schemas to `TOOLS` in `tools/voice_tools/__init__.py`
3. Add handlers to `TOOL_MAP` in the same file
4. Add guidance to `SYSTEM_PROMPT` in `voice/system_prompt.py`
5. If the tool is slow (>2s), add it to `_HEAVY_TOOLS` in `voice/pipeline.py`

## Adding a new agent

1. Create `agents/your_agent.py` extending `BaseAgent`
2. Define `name`, `SYSTEM_PROMPT`, `TOOLS`, and `TOOL_MAP`
3. Register the agent in `main.py` and `core/router.py`
4. Add agent routing keywords to `_KEYWORD_ROUTES` in `core/router.py`

## Reporting bugs

Open a GitHub issue with:
1. What you were doing
2. What you expected
3. What happened (paste the traceback)
4. Your OS and Python version

## Security issues

Do **not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md).
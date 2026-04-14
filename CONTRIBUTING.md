# Contributing to JARVIS

Thanks for your interest in contributing. JARVIS is an open-source, Iron Man-style personal AI assistant. Contributions are welcome — read this before opening a PR.

## Ground rules

- Be respectful. This project has a [Code of Conduct](CODE_OF_CONDUCT.md) — we follow the Contributor Covenant.
- One concern per PR. Small, focused PRs are reviewed faster.
- Tests are required for new features and bug fixes.

## Development setup

```bash
git clone https://github.com/your-username/jarvis.git
cd jarvis
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your own API keys in .env
```

### Required API keys (minimum to run)

| Key | Where to get it |
|-----|----------------|
| `DEEPGRAM_API_KEY` | [console.deepgram.com](https://console.deepgram.com) |
| `DEEPSEEK_API_KEY` | [platform.deepseek.com](https://platform.deepseek.com) |
| `CARTESIA_API_KEY` | [cartesia.ai](https://cartesia.ai) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Cloud Console → OAuth 2.0 |

## Project structure

```
agents/         Per-domain AI agents (calendar, coding, research, etc.)
auth/           Google OAuth flow
core/           Pipeline orchestration, memory, routing, onboarding
shared/         MemPalace memory adapter (ChromaDB + KG + profile)
tools/          Tool implementations (Google APIs, docs, terminal, etc.)
voice/          Pipecat voice pipeline, auth gate
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

- [ ] Passes `python -m pytest` (or existing tests still pass)
- [ ] No hardcoded secrets, personal paths, or API keys
- [ ] `shell=False` on all `subprocess.run()` calls
- [ ] New tools are added to the relevant agent's `TOOL_MAP`
- [ ] `.env.example` updated if you added a new env var

## Reporting bugs

Open a GitHub issue with:
1. What you were doing
2. What you expected
3. What happened (paste the traceback)
4. Your OS and Python version

## Security issues

Do **not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md).

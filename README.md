# JARVIS

> **J**ust **A** **R**ather **V**ery **I**ntelligent **S**ystem

A voice-first, multi-agent AI assistant for macOS — inspired by Iron Man's JARVIS.

## Features

- 🎙️ **Voice Pipeline** — Deepgram STT → GPT-4.1 → Cartesia TTS with real-time interruption
- 🧠 **Brain Router** — 3-tier routing (keyword scoring → LLM classifier → compound decomposition)
- 🤖 **8 Specialist Agents** — System, Research, Writer, Calendar, Coding, Claude, GitHub, Deploy
- 🏗️ **AWS Monitor** — Real Lightsail/EC2 monitoring via boto3 with CloudWatch metrics
- 📝 **Document Engine** — Create, edit, and export documents in 5 formats (md/pdf/docx/html/txt)
- 🔬 **Deep Research** — Multi-source research with Crawl2RAG, market analysis, meeting prep
- 🧠 **MemPalace Memory** — ChromaDB semantic search + SQLite knowledge graph with auto fact extraction
- 🔒 **Voice Auth** — Passphrase gate with SHA-256 + lockout
- 📊 **HUD** — Real-time WebSocket dashboard at `ws://localhost:7788`

## Quickstart

```bash
# 1. Clone
git clone https://github.com/akkupratap323/Multi-Agent-AI-Operations-Platform.jar
cd Multi-Agent-AI-Operations-Platform

# 2. Install deps
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Fill in your API keys

# 4. Run
python main.py          # Voice mode (wake word → voice pipeline)
python main.py --text   # Text mode (terminal chat)
```

## Architecture

```
main.py
├── Voice Mode
│   └── jarvis_pipeline.py → voice/
│       ├── auth_gate.py      (passphrase verification)
│       ├── pipeline.py       (JarvisProcessor + run_pipeline)
│       ├── hud_server.py     (WebSocket broadcast)
│       ├── mute_strategies.py (echo prevention)
│       └── system_prompt.py  (persona + dynamic builder)
│
├── Text Mode
│   └── BrainRouter → 8 Agents
│       ├── SystemAgent      (Mac control)
│       ├── ResearchAgent    (web search, deep research)
│       ├── WriterAgent      (document creation, export)
│       ├── CalendarAgent    (Gmail + Calendar)
│       ├── CodingAgent      (bash, file ops)
│       ├── ClaudeAgent      (DeepSeek + Claude Code MCP)
│       ├── GitHubMonitor    (repo tracking, releases)
│       └── DeployMonitor    (AWS + deploy monitoring)
│
├── Tools (10 domain modules)
│   └── tools/voice_tools/
│       ├── system.py, music.py, desktop.py
│       ├── research.py, github_tool.py
│       ├── deploy.py, writer.py
│       └── comms.py, shell.py, memory_tool.py
│
└── Memory
    └── MemPalace (ChromaDB + SQLite KG)
        └── auto fact extraction per turn
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | DeepSeek V3 (agents), GPT-4.1 (voice) |
| STT | Deepgram Nova-2 |
| TTS | Cartesia Sonic |
| Wake Word | OpenWakeWord (ONNX) |
| Audio Framework | Pipecat |
| Memory | ChromaDB + SQLite KG |
| Search | Tavily API |
| Cloud | AWS (boto3) |
| GitHub | REST API (urllib) |

## License

MIT — see [LICENSE](LICENSE)

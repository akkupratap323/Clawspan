# Clawspan — Your Personal AI Chief of Staff, Running on Your Mac

> A voice-first, always-on AI servant that thinks like a co-founder.  
> Built from scratch — no LangChain, no CrewAI, no agentic framework.  
> Every part of the brain is hand-written Python. Pipecat handles voice I/O only.

---

## What is Clawspan?

Clawspan is a voice-controlled AI assistant that lives on your Mac and acts like a co-founder who knows everything about you. You speak to it, it thinks, it acts — terminal commands, GitHub PRs, AWS health checks, deep research, structured docs, Gmail, Calendar. All through your voice.

Most voice assistants wait for a command and read back a raw API response. Clawspan is different:

- Heavy tools announce themselves before running ("Digging into it now, boss.")
- Results are compressed into 2-3 natural spoken sentences — no raw dumps reach TTS
- Created documents auto-open on screen the moment they're ready
- Tools run sequentially with live status, not in chaotic parallel
- It **learns facts about you** across sessions via a ChromaDB-backed Memory Palace that gets smarter every conversation
- A **passphrase gate** (SHA-256 + salt + lockout) protects access before any agent can run

This is not a wrapper around an existing AI platform. The intent routing, multi-agent orchestration, memory system, tool dispatch, and voice UX are all written from the ground up.

---

## Full Architecture

```mermaid
flowchart TD
    User(["👤 User"])

    subgraph SECURITY ["🔒 Security Gate"]
        direction TB
        AuthInput["Type Passphrase"]
        AuthCheck["SHA-256 + Salt Verify\ncore/auth.py"]
        Lockout["3 attempts → 60s lockout\n~/.clawspan_auth.json"]
        AuthInput --> AuthCheck
        AuthCheck -->|"wrong × 3"| Lockout
    end

    subgraph VOICE ["🎙️ Voice Layer — Pipecat transport only"]
        direction LR
        Mic["🎤 Microphone"]
        VAD["Silero VAD\nsilence detection"]
        STT["Deepgram nova-2\nSpeech → Text"]
        JP["ClawspanProcessor\nvoice/pipeline.py"]
        TTS["Cartesia Sonic\nText → Speech"]
        Speaker["🔊 Speaker"]
        Mic --> VAD --> STT --> JP --> TTS --> Speaker
    end

    subgraph BRAIN ["🧠 Brain Layer — hand-rolled, zero framework"]
        direction TB

        subgraph ROUTER ["BrainRouter — core/router.py"]
            T1["Tier 1: Keyword Pattern Score\n~0ms — no LLM needed"]
            T2["Tier 2: LLM Context Classifier\n~0.3s — only when ambiguous"]
            T3["Tier 3: Multi-intent Decompose\n~0.5s — compound requests"]
            T1 -->|"confidence < threshold"| T2
            T2 -->|"has connectors: and, then, also"| T3
        end

        subgraph AGENTS ["Domain Agents — all extend BaseAgent"]
            direction LR
            SysA["⚙️ SystemAgent\nMac control, terminal\napps, mouse, clipboard"]
            ResA["🔬 ResearchAgent\nDeep research\ncompany + market analysis"]
            WriA["📝 WriterAgent\nDocs, briefs, reports\nMarkdown / PDF / DOCX"]
            CalA["📅 CalendarAgent\nGmail + Google Calendar\nsend, search, schedule"]
            CodA["💻 CodingAgent\nClaude-powered\ncode, debug, refactor"]
            ClaA["🤖 ClaudeAgent\nAnthropic Claude\ncomplex reasoning"]
            DepA["☁️ DeployMonitorAgent\nAWS Lightsail, cost\nSSL, health checks"]
            GHR["GitHub Sub-Router\ncore/github_router.py"]
            GHMon["👁️ GitHubMonitorAgent\ntrack repos, releases\nread-only"]
            GHAct["⚡ GitHubActionAgent\nissues, PRs, stars\nwrite operations"]
            GHR --> GHMon & GHAct
        end

        BASE["BaseAgent — core/base_agent.py\nTool-calling loop · DSML leak recovery\nauto fact extraction after every turn"]

        ROUTER --> SysA & ResA & WriA & CalA & CodA & ClaA & DepA & GHR
        SysA & ResA & WriA & CalA & CodA & ClaA & DepA --> BASE
    end

    subgraph LLM_LAYER ["⚡ LLM Layer — multiple models, different roles"]
        DS["DeepSeek V3\nAll domain agents\ncheap + fast reasoning"]
        GPT4O["GPT-4o\nVoice pipeline LLM\nlow-latency turns"]
        GPT4OMINI["GPT-4o-mini\nFact extraction only\n~$0.0001 per turn"]
        CLAUDE["Anthropic Claude\nCodingAgent only\ncomplex code tasks"]
        EMB["text-embedding-3-small\nMemPalace semantic search\nfact similarity"]
    end

    subgraph MEMORY ["🏛️ Memory Palace — ~/.mempalace/"]
        direction TB

        subgraph LAYERS ["4-Layer Memory Architecture"]
            L0["L0 Identity Layer\nidentity.txt — always loaded\n~100 tokens, fast boot"]
            L1["L1 Importance Layer\ntop-10 facts by importance score\n~500 tokens, every session"]
            L2["L2 Semantic Layer\nquery-relevant facts via cosine sim\n~200 tokens, per-turn"]
            L3["L3 Knowledge Graph\nSQLite entities + triples\nstructured relationships"]
        end

        subgraph STORES ["Dual Storage"]
            CHROMA["ChromaDB\npalace/chroma.sqlite3\ncollection: mempalace_drawers\nOpenAI embeddings"]
            KG["SQLite KG\nknowledge_graph.sqlite3\nentities · triples\nperson / project / system"]
        end

        subgraph WINGS ["Memory Wings (namespaces)"]
            W1["personal\nidentity, name, role"]
            W2["project\nwork decisions, infra"]
            W3["preference\nhow to behave"]
            W4["reference\nexternal systems"]
        end

        FE["🔍 FactExtractor\ncore/fact_extractor.py\nfire-and-forget after every turn\ngpt-4o-mini · ~$0.0001/turn\ndeduplication via similarity > 0.92"]

        L0 & L1 & L2 --> CHROMA
        L3 --> KG
        CHROMA --> W1 & W2 & W3 & W4
    end

    subgraph AWARENESS ["👁️ AwarenessLoop — proactive monitoring"]
        CAL_CHK["📅 Calendar check\nevery 5 min\nalerts 10-15 min before events"]
        EMAIL_CHK["📧 Email delta\nevery 5 min\nunread count change"]
        BATT_CHK["🔋 Battery level\nevery 5 min\nwarn at 20% + 10%"]
        GH_CHK["🐙 GitHub releases\nevery 6 hours\nnew versions + security advisories"]
        DEP_CHK["☁️ Deploy health\nevery 15 min\ndown · degraded · SSL expiry · latency"]
        NQ["NotificationQueue\npriority: CRITICAL / HIGH / MEDIUM / LOW\nchecked before every request"]
        CAL_CHK & EMAIL_CHK & BATT_CHK & GH_CHK & DEP_CHK --> NQ
    end

    subgraph TOOLS ["🛠️ Tools Layer — tools/voice_tools/"]
        direction LR
        TSys["system.py\nterminal · apps\nChrome · clipboard\nvolume · brightness"]
        TDesk["desktop.py\nFinder · mouse\nAI-vision clicks\nscreen describe"]
        TGH["github_tool.py\nfull R/W surface\nissues · PRs\ninsights · advisories"]
        TDep["deploy.py\nAWS Lightsail\nhealth · cost · SSL\nnetwork stats"]
        TRes["research.py\ndeep / company / market\ncrawl2RAG\nmeeting prep"]
        TWri["writer.py\ncompany briefs\nmarket analyses\ncustom docs"]
        TCom["comms.py\nGmail\nGoogle Calendar"]
        TMus["music.py\nApple Music\nYouTube Music"]
        TMem["memory_tool.py\nMemPalace R/W\nfrom voice commands"]
        TSh["shell.py\nraw shell\nescape hatch"]
    end

    subgraph PERSISTENCE ["💾 Persistence — local files"]
        PROF["~/.clawspan_profile.json\nUserProfile\nname · timezone · skills\ngoals · tech stack"]
        AUTH_FILE["~/.clawspan_auth.json\nSHA-256 + salt hash\nfailed attempts\nlockout timestamp"]
        MEM_DIR["~/.mempalace/\npalace/ ChromaDB\nknowledge_graph.sqlite3\nidentity.txt"]
    end

    %% Main flow
    User -->|"speaks"| SECURITY
    AuthCheck -->|"✅ access granted"| VOICE
    JP -->|"user text + tool calls"| BRAIN
    ROUTER --> NQ
    BASE --> LLM_LAYER
    BASE --> TOOLS
    BASE -->|"extract facts async"| FE
    FE --> CHROMA & KG
    BRAIN -->|"inject L0+L1+L2 context"| MEMORY
    AWARENESS --> NQ
    JP -->|"system prompt per turn"| MEMORY

    %% Persistence links
    BASE --> PROF
    AuthCheck --> AUTH_FILE
    CHROMA & KG --> MEM_DIR

    %% LLM routing
    DS -.->|"domain agents"| BASE
    GPT4O -.->|"voice pipeline"| JP
    GPT4OMINI -.->|"fact extraction"| FE
    CLAUDE -.->|"coding tasks"| CodA
    EMB -.->|"embeddings"| CHROMA

    classDef security fill:#7f1d1d,stroke:#ef4444,color:#fff
    classDef voice fill:#1e3a5f,stroke:#3b82f6,color:#fff
    classDef brain fill:#1a2e1a,stroke:#22c55e,color:#fff
    classDef memory fill:#2d1b69,stroke:#a78bfa,color:#fff
    classDef tools fill:#1c1917,stroke:#a8a29e,color:#fff
    classDef llm fill:#451a03,stroke:#f97316,color:#fff
    classDef awareness fill:#0c2340,stroke:#38bdf8,color:#fff
    classDef persist fill:#1c1917,stroke:#78716c,color:#fff

    class SECURITY,AuthInput,AuthCheck,Lockout security
    class VOICE,Mic,VAD,STT,JP,TTS,Speaker voice
    class BRAIN,ROUTER,AGENTS,BASE,T1,T2,T3,SysA,ResA,WriA,CalA,CodA,ClaA,DepA,GHR,GHMon,GHAct brain
    class MEMORY,LAYERS,STORES,WINGS,L0,L1,L2,L3,CHROMA,KG,W1,W2,W3,W4,FE memory
    class TOOLS,TSys,TDesk,TGH,TDep,TRes,TWri,TCom,TMus,TMem,TSh tools
    class LLM_LAYER,DS,GPT4O,GPT4OMINI,CLAUDE,EMB llm
    class AWARENESS,CAL_CHK,EMAIL_CHK,BATT_CHK,GH_CHK,DEP_CHK,NQ awareness
    class PERSISTENCE,PROF,AUTH_FILE,MEM_DIR persist
```

---

## Why No Agentic Framework?

Frameworks like LangChain, AutoGen, and CrewAI are powerful for demos. For a real-time voice assistant they introduce problems that are hard to paper over:

| | Framework | Clawspan |
|---|---|---|
| **Latency** | 100–300 ms of abstraction overhead per hop | Direct async Python — zero middleware |
| **Tool shape** | Framework normalises arguments, you lose control | Raw OpenAI function schemas, you define everything |
| **Memory** | Fragile vector-store integrations, hard to tune | Hand-rolled MemPalace — ChromaDB + SQLite KG |
| **Voice UX** | No concept of heavy vs light tools | `_HEAVY_TOOLS` frozenset, progress ACKs, LLM summariser gate |
| **Routing** | LLM call for every message | Tier 1 keyword scoring — ~0 ms, no LLM needed for 80% of requests |
| **Debugging** | Stack traces through 3 libraries you don't control | Your code all the way down |
| **Memory learning** | Generic — doesn't know who the user is | `FactExtractor` extracts personal facts after **every turn**, gets smarter over time |

> Pipecat is used for one specific reason: streaming mic → STT → TTS → speaker with VAD + turn detection. That's it. Everything above the transport layer is hand-written.

---

## How Clawspan Learns From You

Every conversation makes Clawspan smarter about you. Here's the exact flow:

```mermaid
sequenceDiagram
    participant U as 👤 User
    participant JP as ClawspanProcessor
    participant BA as BaseAgent
    participant FE as FactExtractor
    participant MP as MemPalace

    U->>JP: "I'm building a multi-agent voice assistant at IIIT Nagpur"
    JP->>BA: route + think()
    BA->>BA: LLM generates reply
    BA-->>JP: spoken response
    JP-->>U: 🔊 Clawspan speaks

    Note over BA,FE: fire_and_forget() — non-blocking
    BA->>FE: user_text + assistant_reply (async task)
    FE->>FE: gpt-4o-mini extracts facts
    Note over FE: {"key": "current_project",<br/>"value": "Boss is building a multi-agent<br/>voice assistant at IIIT Nagpur",<br/>"wing": "project", "importance": 4}
    FE->>FE: similarity check — skip if duplicate
    FE->>MP: save_fact(key, value, wing, importance)
    MP->>MP: embed with text-embedding-3-small
    MP->>MP: upsert to ChromaDB by SHA-256(key)
    MP->>MP: add_triple("current_project", "is_about", "voice assistant")

    Note over MP,JP: Next session
    JP->>MP: build_memory_context()
    MP-->>JP: L0 identity + L1 top-10 by importance + L2 query-relevant
    JP->>BA: system prompt includes all learned facts
```

Facts are tagged into four wings: `personal` (who you are), `project` (what you're building), `preference` (how you want Clawspan to behave), `reference` (external systems you use). They persist across restarts, update in place, and are deduplicated by semantic similarity.

---

## Security Gate

Before any agent runs, Clawspan requires authentication.

```mermaid
flowchart LR
    Start(["python main.py"]) --> IsSetup{"passphrase\nset?"}
    IsSetup -->|"no"| Onboard["First-run setup\nonboarding.py\ncollect name, GitHub,\ntimezone, skills"]
    IsSetup -->|"yes"| EnterPW["Enter passphrase\ntext input"]
    EnterPW --> Normalize["Normalize\nlowercase · strip punctuation\nreplace spelled numbers"]
    Normalize --> Hash["SHA-256 + stored salt\ncore/auth.py"]
    Hash -->|"match"| Access["✅ Access granted\nAwarenessLoop starts\nMemPalace loads\nAgents ready"]
    Hash -->|"no match"| Counter{"attempts\n< 3?"}
    Counter -->|"yes"| EnterPW
    Counter -->|"no"| Lockout["🔒 60s lockout\nstored in\n~/.clawspan_auth.json"]
    Lockout --> EnterPW
    Onboard --> SetPW["Set passphrase\n+ confirm"] --> Access
```

Password is stored as SHA-256 + random 16-byte salt in `~/.clawspan_auth.json`. Plaintext is never stored or logged. The normalizer handles voice STT quirks — spelled-out numbers ("iron man mark fifty"), punctuation, extra whitespace — so the same passphrase works whether typed or spoken.

---

## BrainRouter — 3-Tier Routing

```mermaid
flowchart TD
    Input["User request"] --> T1

    subgraph T1 ["Tier 1 — Pattern Scoring ~0ms"]
        Score["Score ALL 7 routes\nagainst keyword lists\nsystem · research · writer\ncalendar · coding · github · deploy"]
        High{"top score ≥ 2.0\nAND 2× second score?"}
        Score --> High
    end

    High -->|"yes — high confidence"| Route["Route to agent"]
    High -->|"no — ambiguous"| Compound

    subgraph Compound ["Tier 3 check"]
        HasConn{"contains: and · then\nalso · plus · next · after that?"}
    end

    HasConn -->|"yes"| T3
    HasConn -->|"no"| T2

    subgraph T3 ["Tier 3 — Multi-intent ~0.5s"]
        Split["Split on connector words\nroute each part separately\npass previous result as context"]
    end

    subgraph T2 ["Tier 2 — LLM Classify ~0.3s"]
        LLMCtx["Context-aware LLM call\nDeepSeek · max_tokens=5\ninjects: Chrome open?\nlast agent used?\nlast search?"]
    end

    T2 --> Route
    T3 --> Route

    Route --> GHCheck{"github route?"}
    GHCheck -->|"yes"| GHRouter["GitHubRouter\nmonitor vs action\nkeyword split"]
    GHCheck -->|"no"| Agent["Domain Agent\nthink()"]
    GHRouter --> GHMon["MonitorAgent\nread-only ops"] & GHAct["ActionAgent\nwrite ops"]
```

Tier 1 handles ~80% of requests at near-zero cost. Tier 2 fires only when the top two keyword scores are within 20% of each other. Tier 3 fires when connector words suggest the user wants two different things done in sequence.

---

## Memory Palace — 4-Layer Architecture

```mermaid
flowchart TB
    subgraph LOAD ["Context Loading — every session start"]
        L0["L0 — Identity\nidentity.txt always loaded\n~100 tokens\nfast boot, no embedding query"]
        L1["L1 — Importance\ntop-10 facts by importance score\n~500 tokens\nloaded regardless of query"]
        L2["L2 — Semantic\nquery-relevant via cosine similarity\n~200 tokens\nfired per-turn with query hint"]
        L3["L3 — Knowledge Graph\nSQLite entity + triple lookup\nstructured relationships\nperson · project · system"]
        L0 --> L1 --> L2 --> L3
    end

    subgraph STORE ["Dual Storage"]
        direction LR
        CHROMA["ChromaDB\npalace/chroma.sqlite3\ncollection: mempalace_drawers\nembedded with text-embedding-3-small\nupserted by SHA-256 key hash"]
        KG["SQLite KG\nknowledge_graph.sqlite3\nentities table\ntriples table\nvalid_from timestamp"]
    end

    subgraph WINGS ["4 Wings / Namespaces"]
        direction LR
        W1["🧍 personal\nidentity · name · location\nrole · background"]
        W2["🏗️ project\ninfrastructure decisions\narchitecture · deadlines\nrepo names"]
        W3["⚙️ preference\nhow to respond\ntools to use\ncommunication style"]
        W4["🔗 reference\nexternal systems\nGitHub repos\nAWS services · APIs"]
    end

    subgraph EXTRACT ["Auto-Extraction Pipeline"]
        TURN["Every conversation turn"] --> FIRE["fire_and_forget()\nnon-blocking task\nvoice response never waits"]
        FIRE --> LLMX["gpt-4o-mini call\n~300 tokens\n~$0.0001/turn\nJSON structured output"]
        LLMX --> DEDUP["Deduplication\nsemantic similarity > 0.92\nkey collision check"]
        DEDUP -->|"new fact"| SAVE["save_fact()\nkey · value · wing · importance 1-5"]
        DEDUP -->|"duplicate"| DROP["skip"]
        SAVE --> CHROMA & KG
    end

    LOAD --> CHROMA & KG
    WINGS --> CHROMA
```

---

## Agent Connections & Delegation

```mermaid
flowchart LR
    BR["BrainRouter"]
    AW["AwarenessLoop\n🔔 NotificationQueue"]

    BR -->|"checked before\nevery request"| AW

    BR --> SYS["SystemAgent"]
    BR --> RES["ResearchAgent"]
    BR --> WRI["WriterAgent"]
    BR --> CAL["CalendarAgent"]
    BR --> COD["CodingAgent"]
    BR --> CLA["ClaudeAgent"]
    BR --> DEP["DeployMonitorAgent"]
    BR --> GHR["GitHubRouter"]
    GHR --> MON["GitHubMonitorAgent"]
    GHR --> ACT["GitHubActionAgent"]

    RES -->|"delegate writing"| WRI
    WRI -->|"delegate research"| RES
    COD -->|"delegate terminal"| SYS
    DEP -->|"delegate AWS tools"| SYS

    subgraph BASELOOP ["BaseAgent tool-calling loop (all agents)"]
        TOOLS_EXEC["execute tool"] --> LLM_CALL["LLM call"]
        LLM_CALL -->|"tool_calls"| TOOLS_EXEC
        LLM_CALL -->|"text response"| FACT_EX["FactExtractor\nasync"]
        FACT_EX --> MEMPALACE["MemPalace"]
    end

    SYS & RES & WRI & CAL & COD & CLA & DEP & MON & ACT --> BASELOOP
```

Agents can delegate sub-tasks to each other through the router (max depth 3 to prevent loops). The ResearchAgent can hand off a finished research brief to the WriterAgent to format it as a document. The CodingAgent can hand off shell commands to the SystemAgent.

---

## Why It's Fast

| Bottleneck | Typical framework | Clawspan |
|---|---|---|
| Intent routing | LLM call every time ~300-500ms | Keyword score ~0ms for 80% of requests |
| Tool dispatch | Serialised through framework abstractions | Direct Python function call |
| Memory read | Re-embedding query on every turn | L0 identity cached in file, L1 pre-sorted by importance |
| Memory write | Blocking call in response path | `fire_and_forget()` — non-blocking asyncio task |
| Voice response | Waits for full tool result | Streams sentences to TTS as they arrive via `_SENTENCE_END` regex |
| Tool result to voice | Raw output piped to TTS | `_summarise_for_voice()` compresses to 1-3 sentences before TTS |
| GitHub warmup | Cold lookup per request | `GitHubAccountCache` pre-warms pinned repos at boot |

---

## Capabilities

### Mac Control

| What you say | What happens |
|---|---|
| "Open VS Code" | `open_app` launches it instantly |
| "Run git status in terminal" | `run_terminal` executes, reports back in 1 sentence |
| "Take a screenshot" | `system_control` saves to Desktop |
| "Click the blue button on screen" | `mouse_control` → GPT-4o vision finds and clicks it |
| "What's on my screen right now" | `describe_screen` → GPT-4o vision describes everything visible |
| "Copy the last thing you said" | `clipboard` writes to macOS clipboard |
| "Find my CV in Documents" | `finder_control` Spotlight search by name |
| "Set volume to 40" | `system_control` adjusts system volume |

### GitHub (Full Read / Write)

| What you say | What happens |
|---|---|
| "Show my repos" | Lists your GitHub repos with descriptions |
| "What should I work on in jarvis" | `repo_insights` — risk scan, open issues, stale PRs |
| "Create an issue in clawspan about the auth bug" | Creates issue with title and body |
| "Track langchain-ai/langchain" | Adds to tracked repos, monitors releases |
| "Any updates from tracked repos" | Checks all tracked for new releases |
| "Search code for BaseAgent" | GitHub code search across all repos |
| "Check security advisories on jarvis" | Pulls advisory list |

### AWS & Deployments

| What you say | What happens |
|---|---|
| "What's my AWS status" | Lightsail instances, IPs, running state |
| "How's my server doing" | Health check on the named service |
| "How much am I spending on AWS" | Cost breakdown from Cost Explorer |
| "Is my site up" | HTTP health check + latency |
| "Check SSL for mycoolsite.com" | Certificate expiry + issuer |

### Research & Documents

| What you say | What happens |
|---|---|
| "Research Raga AI and save a doc" | Confirms → deep research → structured company brief → auto-opens on screen |
| "Market analysis for Tesla" | Market data, analyst sentiment, competitors → saves doc |
| "What is RAG, explain it properly" | `deep_research` → 2-3 spoken sentences + structured doc if asked |
| "Crawl docs.pipecat.ai into memory" | `crawl_to_rag` indexes the whole site into ChromaDB |

### Memory Palace

| What you say | What happens |
|---|---|
| "Remember I prefer TypeScript over JavaScript" | `memory_tool` saves tagged preference fact |
| "What do you know about my stack" | Semantic search across all saved facts |
| "I'm working on a multi-agent voice assistant" | Auto-extracted as a project fact — no explicit command |

---

## Voice UX Design

### Sequential tool dispatch
Tools run one at a time. If you ask Clawspan to "research Raga AI and write a doc":

1. **Confirms:** "Want me to research Raga AI and save a doc, boss?"
2. **Announces:** "Drafting the doc now." — spoken immediately while the heavy tool runs in background
3. **Summarises:** LLM compresses result into 2-3 natural sentences
4. **Opens:** "Your doc is saved as Raga AI Company Research.md and I've opened it for you, boss." — file opens on screen

### Heavy vs light tools
```python
_HEAVY_TOOLS = frozenset({
    "deep_research", "research_company", "market_research",
    "meeting_prep", "agentic_research", "crawl_to_rag",
    "writer_create", "writer_export", "repo_insights",
})
```
Heavy tools get a spoken progress ACK before they run and a full LLM summarisation after. Light tools (web search, terminal, clipboard) get a single-sentence confirmation.

### Echo suppression
`PostSpeechMuteStrategy` keeps the mic muted for 800 ms after Clawspan stops speaking, preventing Clawspan from hearing its own TTS output and responding to itself.

---

## Project Structure

```
clawspan/
│
├── main.py                     Entry — --text for terminal, default for voice
├── clawspan_pipeline.py          Thin shim → voice/pipeline.py
├── clawspan_tools.py             Thin shim → tools/voice_tools/
├── config.py                   API keys from .env
├── wake_word.py                "Hey Clawspan" (OpenWakeWord + ONNX)
│
├── voice/                      Voice pipeline (Pipecat transport only)
│   ├── pipeline.py             ClawspanProcessor + run_pipeline()
│   ├── system_prompt.py        SYSTEM_PROMPT + dynamic prompt builder per turn
│   ├── auth_gate.py            Passphrase gate
│   ├── mute_strategies.py      PostSpeechMuteStrategy
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
│   ├── awareness.py            AwarenessLoop — calendar / email / battery / GitHub / deploys
│   ├── auth.py                 SHA-256 + salt passphrase + lockout
│   ├── onboarding.py           First-run profile setup
│   ├── response.py             Response filter (strips raw tool dumps from voice)
│   └── prompts.py              Shared personality + response rules
│
├── agents/                     Domain agents (all extend BaseAgent)
│   ├── system_agent.py
│   ├── research_agent.py
│   ├── writer_agent.py
│   ├── calendar_agent.py
│   ├── coding_agent.py
│   ├── claude_agent.py
│   ├── deploy_monitor_agent.py
│   ├── github_monitor_agent.py
│   └── github_action_agent.py
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

---

## Stack

| Component | Library | Role |
|---|---|---|
| Voice transport | Pipecat | Mic/speaker streaming, VAD, turn management — **voice I/O only** |
| Speech-to-text | Deepgram nova-2 | High-accuracy STT with smart formatting |
| Text-to-speech | Cartesia Sonic | Ultra-low-latency neural TTS |
| Wake word | OpenWakeWord (ONNX) | Local "Hey Clawspan" detection |
| LLM — voice pipeline | OpenAI gpt-4o | Low-latency voice turns |
| LLM — all agents | DeepSeek V3 | Fast, cheap domain agent reasoning |
| LLM — fact extraction | OpenAI gpt-4o-mini | ~$0.0001/turn background extraction |
| LLM — coding | Anthropic Claude | CodingAgent complex code tasks |
| Embeddings | OpenAI text-embedding-3-small | MemPalace semantic search |
| Vector store | ChromaDB | Persistent local semantic memory |
| Knowledge graph | SQLite | Entity + triple store |
| Research | Tavily | Live multi-source web research |
| Screen vision | GPT-4o vision | Describe screen, find click targets |
| Mac automation | PyAutoGUI + AppleScript | Mouse, keyboard, app control |
| AWS | boto3 | Lightsail, CloudWatch, Cost Explorer |

---

## Getting Started

### Prerequisites

- macOS (tested on macOS 15 Sequoia)
- Python 3.11 (`brew install python@3.11`)
- GitHub CLI (`brew install gh`)

### API Keys Required

| Key | Where |
|---|---|
| `OPENAI_API_KEY` | platform.openai.com |
| `DEEPGRAM_API_KEY` | console.deepgram.com |
| `CARTESIA_API_KEY` | cartesia.ai |
| `TAVILY_API_KEY` | tavily.com |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → PAT |
| `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` | console.cloud.google.com |

Optional:

| Key | Purpose |
|---|---|
| `DEEPSEEK_API_KEY` | All domain agents (falls back to OpenAI if unset) |
| `CARTESIA_VOICE_ID` | Override the default British Clawspan voice |

### Install

```bash
git clone https://github.com/akkupratap323/clawspan
cd clawspan
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys
python main.py          # voice mode
python main.py --text   # text mode — no mic/speaker needed
```

### Environment Variables

```env
OPENAI_API_KEY=
DEEPGRAM_API_KEY=
CARTESIA_API_KEY=
TAVILY_API_KEY=
GITHUB_TOKEN=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
DEEPSEEK_API_KEY=           # optional
CARTESIA_VOICE_ID=          # optional
Clawspan_SKIP_AUTH=1          # skip passphrase gate during development
```

---

## Adding a New Tool Domain

1. Create `tools/voice_tools/your_domain.py` with `exec_*` functions
2. Add OpenAI function schemas to `TOOLS` in `tools/voice_tools/__init__.py`
3. Add handlers to `TOOL_MAP` in the same file
4. Add guidance to `SYSTEM_PROMPT` in `voice/system_prompt.py`
5. If the tool is slow (>2 s), add it to `_HEAVY_TOOLS` in `voice/pipeline.py` and give it a progress line in `_HEAVY_PROGRESS_ACK`

---

## Status

Active development. Voice pipeline, BrainRouter, MemPalace, and all tool integrations are working. Open-sourcing in progress.

Built by [@akkupratap323](https://github.com/akkupratap323).

---

## License

MIT

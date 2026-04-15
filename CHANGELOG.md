# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `pyproject.toml` for standard Python packaging metadata (with `dev` optional deps)
- Graceful degradation for missing optional dependencies in text mode
- Runtime enforcement of `confirm` parameter for destructive shell commands
- macOS-only platform notice in README
- `sounddevice` dependency to `requirements.txt` and `pyproject.toml`

### Changed
- Passphrase input now uses `getpass.getpass()` to hide input on screen (`main.py` and `voice/auth_gate.py`)
- System sound playback uses `subprocess.Popen` instead of `os.system()`
- Banner text updated from "J.A.R.V.I.S." to "Clawspan"
- Removed hardcoded `ap-south-1` default AWS region from `config.py` and `setup.sh`
- CODE_OF_CONDUCT.md contact email updated to author email
- Added `PyAutoGUI`, `openwakeword`, `sounddevice` to `requirements.txt`
- Cleaned up stale `.jarvis_*` references in `.gitignore`
- Renamed all "Jarvis" references to "Clawspan" in HUD (`hud/index.html`)
  - Logo text: JARVIS → CLAWSPAN
  - Footer: JARVIS · NESTER LABS → CLAWSPAN · NESTER LABS
  - JS: `onJarvisEvent` → `onClawspanEvent`, `lastJarvisText` → `lastClawspanText`
  - CSS: `.hist-who.jarvis` → `.hist-who.clawspan`
  - History initials: J → C
- Removed unused `JarvisProcessor` alias from `clawspan_pipeline.py`

### Fixed
- Bare `except Exception` in Google auth replaced with specific error logging
- `utils.py` imports cleaned up (`os` → `subprocess`)
- Mock GitHub token in tests no longer uses `ghp_` prefix (avoids GitHub secret scanning triggers)
- Passphrase terminology consistent (was "password" in `voice/auth_gate.py` text gate)

### Security
- Shell escape-hatch now blocks destructive commands unless `confirm=True` is explicitly set
- Passphrase no longer visible on screen during text-mode authentication

## [0.1.0] - 2026-04-15

### Added
- Initial open-source release
- Voice pipeline (Pipecat + Deepgram STT + Cartesia TTS)
- 3-tier BrainRouter (keyword scoring + LLM classification + multi-intent decomposition)
- MemPalace 4-layer memory (ChromaDB + SQLite knowledge graph)
- 7 domain agents (System, Research, Writer, Calendar, DeepCoder, DeployMonitor, GitHub)
- Full GitHub read/write integration
- AWS/deployment monitoring
- SHA-256 + salt passphrase authentication
- Interactive onboarding flow
- AwarenessLoop background monitoring
- Electron HUD overlay
- CLI wrapper (`clawspan start/text/hud`)

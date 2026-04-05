"""Voice pipeline — realtime STT → LLM → TTS orchestration.

Modules:
- hud_server: WebSocket broadcast for the HUD frontend
- mute_strategies: custom Pipecat mute strategies (echo prevention)
- system_prompt: personality + dynamic prompt builder
- turn_handler: streaming LLM turn + tool dispatch
- auth_gate: voice passphrase verification at startup
- pipeline: top-level orchestrator (run_pipeline)
"""

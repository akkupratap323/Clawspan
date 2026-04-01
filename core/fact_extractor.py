"""Auto-extract durable facts from conversation turns and save to MemPalace.

Runs asynchronously after each voice turn. Uses a small, cheap LLM call
(gpt-4o-mini) to pull facts worth remembering — identity, preferences,
decisions, project state — and pushes them into the palace via save_fact().

Design goals:
- Fire-and-forget: never blocks the voice response
- Cheap: ~300 tokens per turn, gpt-4o-mini (~$0.0001/turn)
- Conservative: extract nothing rather than save noise
- Deduplicating: skips facts already present in the palace
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from core.llm import get_client, get_model
from shared.mempalace_adapter import save_fact, search_facts

_EXTRACTOR_PROMPT = """You extract durable facts from a single conversation turn between a user ("boss") and JARVIS (his AI assistant). Output JSON only.

A DURABLE FACT is something worth remembering for future conversations:
- Boss's identity, role, skills, projects, goals
- Boss's preferences (how he wants things done, tools he uses, style)
- Project decisions or state (infrastructure, architecture, deadlines)
- People or external systems he references

NOT durable facts:
- Casual greetings, acknowledgements, small talk
- Tool output echoed back (stats, logs, API responses)
- Questions without answers
- Transient context (current task, temporary state)

Return JSON with this exact shape:
{"facts": [{"key": "<short-identifier>", "value": "<one sentence statement>", "wing": "<personal|project|preference|reference>", "importance": <1-5>}]}

Rules:
- Return {"facts": []} if nothing durable was exchanged
- key: snake_case, specific (e.g., "aws_region", "preferred_response_style"), max 40 chars
- value: one complete sentence, third-person ("Boss prefers X because Y")
- wing: personal (about boss), project (about work), preference (how to behave), reference (external system)
- importance: 5=core identity, 4=strong preference, 3=decision, 2=detail, 1=weak signal
- Max 3 facts per turn. Quality over quantity.
"""


async def extract_and_save(user_text: str, assistant_reply: str) -> list[str]:
    """Extract durable facts from a turn and save them. Returns saved keys."""
    if not user_text.strip():
        return []

    turn = f'BOSS: "{user_text}"\nJARVIS: "{assistant_reply}"'

    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=get_model(),
            messages=[
                {"role": "system", "content": _EXTRACTOR_PROMPT},
                {"role": "user", "content": turn},
            ],
            max_tokens=400,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
    except Exception as e:
        print(f"[FactExtractor] LLM error: {e}", flush=True)
        return []

    try:
        parsed = json.loads(raw)
        facts = parsed.get("facts", [])
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(facts, list):
        return []

    saved: list[str] = []
    for fact in facts[:3]:
        if not isinstance(fact, dict):
            continue
        key = str(fact.get("key", "")).strip()
        value = str(fact.get("value", "")).strip()
        wing = str(fact.get("wing", "personal")).strip() or "personal"
        try:
            importance = int(fact.get("importance", 3))
        except (ValueError, TypeError):
            importance = 3

        if not key or not value or len(value) < 10:
            continue

        key = re.sub(r"[^a-z0-9_]", "_", key.lower())[:40]

        if _is_duplicate(key, value):
            continue

        try:
            save_fact(key=key, value=value, wing=wing, importance=importance)
            saved.append(key)
        except Exception as e:
            print(f"[FactExtractor] save error for {key}: {e}", flush=True)

    if saved:
        print(f"[FactExtractor] Saved {len(saved)} fact(s): {', '.join(saved)}", flush=True)
    return saved


def _is_duplicate(key: str, value: str) -> bool:
    """Skip if the key already exists or a semantically-close fact is stored."""
    try:
        hits = search_facts(value, n_results=3)
    except Exception:
        return False
    for h in hits:
        if h.get("key") == key and h.get("similarity", 0) > 0.7:
            return True
        if h.get("similarity", 0) > 0.92:
            return True
    return False


def fire_and_forget(user_text: str, assistant_reply: str) -> None:
    """Schedule extraction on the running event loop without awaiting."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_safe_extract(user_text, assistant_reply))


async def _safe_extract(user_text: str, assistant_reply: str) -> None:
    try:
        await extract_and_save(user_text, assistant_reply)
    except Exception as e:
        print(f"[FactExtractor] background error: {e}", flush=True)

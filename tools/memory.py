"""Persistent memory — MemPalace-powered semantic memory.

Used by:
  - Voice pipeline (jarvis_tools.py) for save/recall/forget
  - Agents (via memory_tool) for personal fact storage
  - BaseAgent for session context

Backend: ChromaDB (semantic search) + SQLite knowledge graph (entities).
"""

from __future__ import annotations

from shared.mempalace_adapter import (
    save_fact,
    search_facts,
    delete_fact,
    get_all_facts,
    add_entity,
    add_triple,
    query_entity,
)


def save(key: str, value: str) -> str:
    """Save a key-value pair to memory."""
    save_fact(key, value)
    return f"Remembered: {key} = {value}"


def recall(query: str) -> str:
    """Semantic search across all memories."""
    hits = search_facts(query, n_results=5)
    if not hits:
        return f"Nothing saved about '{query}'."
    lines = []
    for h in hits:
        if h["similarity"] > 0.2:
            lines.append(f"- {h['text']} (match: {h['similarity']})")
    return "\n".join(lines) if lines else f"Nothing relevant about '{query}'."


def list_all() -> str:
    """List all saved memories."""
    facts = get_all_facts()
    named = {k: v for k, v in facts.items() if not k.startswith("__")}
    if not named:
        return "Memory is empty."
    lines = [f"- {k}: {v['value']}" for k, v in list(named.items())[:20]]
    return "\n".join(lines)


def forget(key: str) -> str:
    """Delete a memory entry."""
    if delete_fact(key):
        return f"Forgotten: {key}"
    return f"No memory for '{key}'."

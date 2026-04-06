"""Memory voice tool: save, recall, list, forget facts."""

from __future__ import annotations

from tools import memory as mem_tool


def exec_memory_tool(action: str, key: str = "", value: str = "", query: str = "", **_kw) -> str:
    """Save or recall personal facts. Actions: save, recall, list, forget."""
    if action == "save":
        return mem_tool.save(key, value)
    if action == "recall":
        return mem_tool.recall(query or key)
    if action == "list":
        return mem_tool.list_all()
    if action == "forget":
        return mem_tool.forget(key)
    return f"Unknown memory action: {action}"

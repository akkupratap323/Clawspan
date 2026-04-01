"""
Shared memory system — used by all JARVIS agents.

Now powered by MemPalace: ChromaDB (semantic search) + SQLite knowledge graph.
This module maintains the same public API so all existing agents work unchanged.

Migration from the old SQLite key-value store happens automatically on first import.
"""

from __future__ import annotations

from shared.mempalace_adapter import (
    # Backward-compatible API (same function signatures as before)
    load_memory,
    save_memory,
    delete_memory,
    search_memory,
    build_memory_context,
    save_session_context,
    # New MemPalace capabilities
    save_fact,
    search_facts,
    delete_fact,
    get_all_facts,
    add_entity,
    delete_entity,
    get_entities_by_type,
    add_triple,
    update_triple,
    query_entity,
    get_identity,
    set_identity,
    migrate_from_legacy_db,
)

# Run migration once on first import
_migrated = False
if not _migrated:
    try:
        migrate_from_legacy_db()
    except Exception:
        pass
    _migrated = True

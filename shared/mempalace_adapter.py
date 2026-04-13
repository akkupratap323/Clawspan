"""
MemPalace adapter — bridges JARVIS memory API to MemPalace's 4-layer stack.

Provides the same interface as shared/memory.py so all agents work unchanged.
Under the hood: ChromaDB (semantic search) + SQLite knowledge graph (entities).

Embedding: OpenAI text-embedding-3-small for high-quality personal fact retrieval.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from config import OPENAI_API_KEY

# ── Paths ────────────────────────────────────────────────────────────────────

MEMPALACE_DIR = os.path.expanduser("~/.mempalace")
PALACE_PATH = os.path.join(MEMPALACE_DIR, "palace")
IDENTITY_PATH = os.path.join(MEMPALACE_DIR, "identity.txt")
KG_PATH = os.path.join(MEMPALACE_DIR, "knowledge_graph.sqlite3")
COLLECTION_NAME = "mempalace_drawers"

# Legacy SQLite (for migration)
LEGACY_MEMORY_DB = os.path.expanduser("~/.jarvis_memory.db")

# ── Ensure dirs exist ────────────────────────────────────────────────────────

os.makedirs(PALACE_PATH, exist_ok=True)
os.makedirs(MEMPALACE_DIR, exist_ok=True)


# ── OpenAI Embedding Function ───────────────────────────────────────────────

class _OpenAIv1EmbeddingFunction(EmbeddingFunction[Documents]):
    """OpenAI text-embedding-3-small via openai>=1.0 SDK.

    Replaces the bundled chromadb OpenAIEmbeddingFunction, which uses the
    removed legacy `openai.Embedding.create()` call and fails on openai>=1.0.
    """

    def __init__(self, api_key: str, model_name: str = "text-embedding-3-small") -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model_name

    def __call__(self, input: Documents) -> Embeddings:
        if not input:
            return []
        response = self._client.embeddings.create(model=self._model, input=list(input))
        return [item.embedding for item in response.data]

    @staticmethod
    def name() -> str:
        # Chroma persists this identifier alongside the collection and refuses
        # to reopen with a mismatched one. The existing palace was created by
        # chromadb's bundled OpenAIEmbeddingFunction (identifier "openai"),
        # so keep the name compatible.
        return "openai"


def _get_embedding_fn() -> _OpenAIv1EmbeddingFunction:
    """OpenAI text-embedding-3-small — 1536-dim, excellent for personal facts."""
    return _OpenAIv1EmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name="text-embedding-3-small",
    )


# ── ChromaDB Collection ─────────────────────────────────────────────────────

_client: chromadb.PersistentClient | None = None
_collection = None


def _get_collection():
    """Get or create the palace ChromaDB collection with OpenAI embeddings.

    Uses ``get_or_create_collection`` which is atomic in chromadb's rust
    backend — avoids the get/except/create race that fires when multiple
    async tasks (fact extractor + memory context builder) initialise the
    collection concurrently on a cold pipeline start.
    """
    global _client, _collection
    if _collection is not None:
        return _collection
    _client = chromadb.PersistentClient(path=PALACE_PATH)
    _collection = _client.get_or_create_collection(
        COLLECTION_NAME,
        embedding_function=_get_embedding_fn(),
    )
    return _collection


# ── Knowledge Graph (SQLite) ────────────────────────────────────────────────

_kg_conn: sqlite3.Connection | None = None


def _get_kg() -> sqlite3.Connection:
    """Get knowledge graph SQLite connection."""
    global _kg_conn
    if _kg_conn is not None:
        return _kg_conn
    _kg_conn = sqlite3.connect(KG_PATH, check_same_thread=False, timeout=10)
    _kg_conn.execute("PRAGMA journal_mode=WAL")
    _kg_conn.row_factory = sqlite3.Row
    _kg_conn.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'unknown',
            properties TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS triples (
            id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            valid_from TEXT,
            valid_to TEXT,
            confidence REAL DEFAULT 1.0,
            source_closet TEXT,
            source_file TEXT,
            extracted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subject) REFERENCES entities(id),
            FOREIGN KEY (object) REFERENCES entities(id)
        );
        CREATE INDEX IF NOT EXISTS idx_triples_subject ON triples(subject);
        CREATE INDEX IF NOT EXISTS idx_triples_object ON triples(object);
        CREATE INDEX IF NOT EXISTS idx_triples_predicate ON triples(predicate);
    """)
    _kg_conn.commit()
    return _kg_conn


def _entity_id(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "")


# ── Core Operations ─────────────────────────────────────────────────────────

def save_fact(key: str, value: str, wing: str = "personal",
              room: str = "general", importance: int = 3) -> str:
    """Save a fact to both ChromaDB (semantic) and KG (structured).

    Returns the drawer ID for linking.
    """
    now = datetime.now()
    drawer_id = f"d_{hashlib.sha256(f'{key}_{now.isoformat()}'.encode()).hexdigest()[:16]}"
    content = f"{key}: {value}"

    # File into ChromaDB
    col = _get_collection()
    col.upsert(
        ids=[drawer_id],
        documents=[content],
        metadatas=[{
            "wing": wing,
            "room": room,
            "key": key,
            "importance": importance,
            "saved_at": now.strftime("%Y-%m-%d %H:%M"),
            "source_file": "jarvis_live",
        }],
    )

    # Add to knowledge graph with source_closet link
    kg = _get_kg()
    sub_id = _entity_id(key)
    obj_id = _entity_id(value[:64])
    with kg:
        kg.execute(
            "INSERT OR IGNORE INTO entities (id, name, type) VALUES (?, ?, ?)",
            (sub_id, key, "fact"),
        )
        kg.execute(
            "INSERT OR IGNORE INTO entities (id, name, type) VALUES (?, ?, ?)",
            (obj_id, value[:64], "value"),
        )
        triple_id = f"t_{sub_id}_is_{obj_id}_{drawer_id[-8:]}"
        kg.execute(
            """INSERT OR REPLACE INTO triples
               (id, subject, predicate, object, valid_from, confidence, source_closet)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (triple_id, sub_id, "is", obj_id,
             now.strftime("%Y-%m-%d"), 1.0, drawer_id),
        )

    return drawer_id


def search_facts(query: str, n_results: int = 5,
                 wing: str | None = None, room: str | None = None) -> list[dict]:
    """Semantic search across all memories. Returns ranked results."""
    col = _get_collection()
    where = {}
    if wing and room:
        where = {"$and": [{"wing": wing}, {"room": room}]}
    elif wing:
        where = {"wing": wing}
    elif room:
        where = {"room": room}

    kwargs: dict[str, Any] = {
        "query_texts": [query],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    try:
        results = col.query(**kwargs)
    except Exception:
        return []

    docs = results["documents"][0] if results["documents"] else []
    metas = results["metadatas"][0] if results["metadatas"] else []
    dists = results["distances"][0] if results["distances"] else []

    hits = []
    for doc, meta, dist in zip(docs, metas, dists):
        hits.append({
            "text": doc,
            "key": meta.get("key", ""),
            "wing": meta.get("wing", "unknown"),
            "room": meta.get("room", "unknown"),
            "similarity": round(1 - dist, 3),
            "saved_at": meta.get("saved_at", ""),
        })
    return hits


def delete_fact(key: str) -> bool:
    """Delete a memory by key from both ChromaDB and KG."""
    col = _get_collection()
    try:
        # Find drawers matching this key
        results = col.get(where={"key": key}, limit=10)
        ids = results.get("ids", [])
        if ids:
            col.delete(ids=ids)

        # Remove from KG
        kg = _get_kg()
        sub_id = _entity_id(key)
        with kg:
            kg.execute("DELETE FROM triples WHERE subject = ?", (sub_id,))
            kg.execute("DELETE FROM entities WHERE id = ?", (sub_id,))
        return bool(ids)
    except Exception:
        return False


def get_all_facts() -> dict[str, dict]:
    """Return all memories as a dict (backward compatible with old API)."""
    col = _get_collection()
    result: dict[str, dict] = {}
    offset = 0
    batch_size = 500

    while True:
        try:
            batch = col.get(
                include=["documents", "metadatas"],
                limit=batch_size,
                offset=offset,
            )
        except Exception:
            break

        docs = batch.get("documents", [])
        metas = batch.get("metadatas", [])
        if not docs:
            break

        for doc, meta in zip(docs, metas):
            key = meta.get("key", doc[:30])
            result[key] = {
                "value": doc,
                "saved_at": meta.get("saved_at", ""),
                "wing": meta.get("wing", ""),
                "room": meta.get("room", ""),
            }
        offset += len(docs)
        if len(docs) < batch_size:
            break

    return result


# ── KG Entity Operations ────────────────────────────────────────────────────

def add_entity(name: str, entity_type: str = "person",
               properties: dict | None = None) -> str:
    """Add an entity to the knowledge graph."""
    eid = _entity_id(name)
    kg = _get_kg()
    with kg:
        kg.execute(
            "INSERT OR REPLACE INTO entities (id, name, type, properties) VALUES (?, ?, ?, ?)",
            (eid, name, entity_type, json.dumps(properties or {})),
        )
    return eid


def add_triple(subject: str, predicate: str, obj: str,
               valid_from: str | None = None, source_closet: str | None = None) -> str:
    """Add a relationship triple to the knowledge graph."""
    sub_id = _entity_id(subject)
    obj_id = _entity_id(obj)
    pred = predicate.lower().replace(" ", "_")
    kg = _get_kg()

    with kg:
        kg.execute(
            "INSERT OR IGNORE INTO entities (id, name) VALUES (?, ?)",
            (sub_id, subject),
        )
        kg.execute(
            "INSERT OR IGNORE INTO entities (id, name) VALUES (?, ?)",
            (obj_id, obj),
        )
        # Check existing
        existing = kg.execute(
            "SELECT id FROM triples WHERE subject=? AND predicate=? AND object=? AND valid_to IS NULL",
            (sub_id, pred, obj_id),
        ).fetchone()
        if existing:
            return existing["id"]

        triple_id = f"t_{sub_id}_{pred}_{obj_id}_{hashlib.sha256(datetime.now().isoformat().encode()).hexdigest()[:8]}"
        kg.execute(
            """INSERT INTO triples (id, subject, predicate, object, valid_from, source_closet)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (triple_id, sub_id, pred, obj_id, valid_from, source_closet),
        )
    return triple_id


def delete_entity(name: str) -> bool:
    """Remove an entity and all its triples from the knowledge graph."""
    eid = _entity_id(name)
    kg = _get_kg()
    with kg:
        kg.execute("DELETE FROM triples WHERE subject = ? OR object = ?", (eid, eid))
        kg.execute("DELETE FROM entities WHERE id = ?", (eid,))
    return True


def get_entities_by_type(entity_type: str) -> list[dict]:
    """Get all entities of a given type (e.g., 'project', 'person')."""
    kg = _get_kg()
    rows = kg.execute(
        "SELECT id, name, type, properties, created_at FROM entities WHERE type = ?",
        (entity_type,),
    ).fetchall()
    results = []
    for row in rows:
        props = {}
        try:
            props = json.loads(row["properties"])
        except (json.JSONDecodeError, TypeError):
            pass
        results.append({
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "properties": props,
            "created_at": row["created_at"],
        })
    return results


def update_triple(subject: str, predicate: str, new_object: str,
                  old_object: str | None = None) -> str:
    """Update a triple's object value. Expires old triple, creates new one.

    If old_object given, only expires that specific triple.
    Otherwise expires all triples matching subject+predicate.
    """
    sub_id = _entity_id(subject)
    pred = predicate.lower().replace(" ", "_")
    kg = _get_kg()
    now = datetime.now().strftime("%Y-%m-%d")

    with kg:
        # Expire old triples
        if old_object:
            old_obj_id = _entity_id(old_object)
            kg.execute(
                "UPDATE triples SET valid_to = ? WHERE subject = ? AND predicate = ? AND object = ? AND valid_to IS NULL",
                (now, sub_id, pred, old_obj_id),
            )
        else:
            kg.execute(
                "UPDATE triples SET valid_to = ? WHERE subject = ? AND predicate = ? AND valid_to IS NULL",
                (now, sub_id, pred),
            )

    # Create new triple
    return add_triple(subject, pred, new_object, valid_from=now)


def query_entity(name: str) -> list[dict]:
    """Get all current relationships for an entity."""
    eid = _entity_id(name)
    kg = _get_kg()
    results = []

    # Outgoing
    for row in kg.execute(
        """SELECT t.*, e.name as obj_name FROM triples t
           JOIN entities e ON t.object = e.id
           WHERE t.subject = ? AND t.valid_to IS NULL""",
        (eid,),
    ).fetchall():
        results.append({
            "subject": name,
            "predicate": row["predicate"],
            "object": row["obj_name"],
            "valid_from": row["valid_from"],
            "source_closet": row["source_closet"],
        })

    # Incoming
    for row in kg.execute(
        """SELECT t.*, e.name as sub_name FROM triples t
           JOIN entities e ON t.subject = e.id
           WHERE t.object = ? AND t.valid_to IS NULL""",
        (eid,),
    ).fetchall():
        results.append({
            "subject": row["sub_name"],
            "predicate": row["predicate"],
            "object": name,
            "valid_from": row["valid_from"],
            "source_closet": row["source_closet"],
        })

    return results


# ── Identity (L0) ───────────────────────────────────────────────────────────

def get_identity() -> str:
    """Read the L0 identity text."""
    if os.path.exists(IDENTITY_PATH):
        with open(IDENTITY_PATH, "r") as f:
            return f.read().strip()
    return ""


def set_identity(text: str) -> None:
    """Write the L0 identity text."""
    with open(IDENTITY_PATH, "w") as f:
        f.write(text)


# ── Context Builders (for agent system prompts) ─────────────────────────────

def build_memory_context(query_hint: str = "") -> str:
    """Build memory context for injection into agent system prompts.

    Uses the 4-layer approach:
    - L0: Identity (always loaded, ~100 tokens)
    - L1: Top memories by importance (~500 tokens)
    - L2: Query-relevant memories if hint provided (~200 tokens)
    """
    parts = []

    # L0: Identity
    identity = get_identity()
    if identity:
        parts.append(f"IDENTITY:\n{identity}")

    # L1: Top important memories (always loaded)
    col = _get_collection()
    try:
        all_data = col.get(
            include=["documents", "metadatas"],
            limit=100,
        )
        docs = all_data.get("documents", [])
        metas = all_data.get("metadatas", [])

        if docs:
            # Sort by importance, take top 10
            scored = []
            for doc, meta in zip(docs, metas):
                imp = meta.get("importance", 3)
                try:
                    imp = float(imp)
                except (ValueError, TypeError):
                    imp = 3.0
                scored.append((imp, meta.get("key", ""), doc))
            scored.sort(key=lambda x: x[0], reverse=True)

            # Filter out session entries
            named = [(k, d) for imp, k, d in scored[:15] if not k.startswith("__")]
            if named:
                lines = [f"  - {k}: {d}" for k, d in named]
                parts.append("REMEMBERED FACTS:\n" + "\n".join(lines))
    except Exception:
        pass

    # L2: Query-relevant (if hint provided)
    if query_hint:
        hits = search_facts(query_hint, n_results=3)
        if hits:
            relevant = [f"  - {h['text']}" for h in hits if h["similarity"] > 0.3]
            if relevant:
                parts.append("RELEVANT MEMORIES:\n" + "\n".join(relevant))

    # KG summary: key entity relationships
    try:
        kg = _get_kg()
        top_triples = kg.execute(
            """SELECT s.name as sub, t.predicate, o.name as obj
               FROM triples t
               JOIN entities s ON t.subject = s.id
               JOIN entities o ON t.object = o.id
               WHERE t.valid_to IS NULL
               ORDER BY t.confidence DESC
               LIMIT 10""",
        ).fetchall()
        if top_triples:
            kg_lines = [f"  - {r['sub']} {r['predicate']} {r['obj']}" for r in top_triples]
            parts.append("KNOWLEDGE GRAPH:\n" + "\n".join(kg_lines))
    except Exception:
        pass

    return "\n\n" + "\n\n".join(parts) if parts else ""


def build_session_context() -> str:
    """Get the last session log from memory (backward compat)."""
    hits = search_facts("__last_session__", n_results=1)
    if hits and hits[0].get("similarity", 0) > 0.5:
        return hits[0]["text"]
    return ""


# ── Backward-Compatible API ─────────────────────────────────────────────────
# These match the old shared/memory.py interface exactly.

def load_memory() -> dict:
    """Load all memories as dict. Backward compatible."""
    return get_all_facts()


def save_memory(data: dict) -> None:
    """Save a full memory dict. Backward compatible."""
    for key, entry in data.items():
        if isinstance(entry, dict):
            value = entry.get("value", "")
        else:
            value = str(entry)
        if value:
            save_fact(key, value)


def delete_memory(key: str) -> bool:
    """Delete a memory entry. Backward compatible."""
    return delete_fact(key)


def search_memory(query: str) -> dict:
    """Semantic search. Backward compatible (returns dict)."""
    hits = search_facts(query, n_results=5)
    result: dict = {}
    for h in hits:
        key = h.get("key", h["text"][:30])
        result[key] = {
            "value": h["text"],
            "saved_at": h.get("saved_at", ""),
            "similarity": h["similarity"],
        }
    return result


def save_session_context(conversation_ref: list, system_prompt: str,
                         user_input: str, reply: str) -> None:
    """Save rolling session log. Backward compatible."""
    # Load existing session
    existing = ""
    hits = search_facts("__last_session__", n_results=1)
    for h in hits:
        if h.get("key") == "__last_session__":
            existing = h["text"].replace("__last_session__: ", "")
            break

    existing_lines = existing.split(" | ") if existing else []
    new_entry = (
        f"[{datetime.now().strftime('%m/%d %H:%M')}] "
        f"You: {user_input[:80]} -> JARVIS: {reply[:80]}"
    )
    existing_lines.append(new_entry)
    existing_lines = existing_lines[-5:]

    save_fact(
        "__last_session__",
        " | ".join(existing_lines),
        wing="system",
        room="session",
        importance=1,
    )

    # Refresh system prompt in conversation with latest memory
    if conversation_ref:
        mem_context = build_memory_context()
        conversation_ref[0]["content"] = system_prompt + mem_context


# ── Migration ────────────────────────────────────────────────────────────────

def migrate_from_legacy_db() -> int:
    """Migrate facts from ~/.jarvis_memory.db (old SQLite) into MemPalace.

    Returns number of migrated entries. Only runs once (marker file).
    """
    marker = os.path.join(MEMPALACE_DIR, ".migrated_from_legacy")
    if os.path.exists(marker):
        return 0
    if not os.path.exists(LEGACY_MEMORY_DB):
        return 0

    try:
        conn = sqlite3.connect(LEGACY_MEMORY_DB)
        rows = conn.execute(
            "SELECT key, value, metadata, saved_at FROM memories"
        ).fetchall()
        conn.close()
    except Exception:
        return 0

    count = 0
    for key, value, metadata, saved_at in rows:
        if not value or key.startswith("__"):
            continue
        try:
            save_fact(key, value, wing="personal", room="migrated", importance=3)
            count += 1
        except Exception:
            continue

    if count > 0:
        print(f"[Memory] Migrated {count} entries from legacy DB to MemPalace.")
        # Write marker so migration doesn't run again
        with open(marker, "w") as f:
            f.write(datetime.now().isoformat())

    return count

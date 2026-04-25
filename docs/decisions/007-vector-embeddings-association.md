# 007 — Lightweight knowledge association via vector embeddings

**Status**: Accepted  
**Date**: 2026-04

## In plain terms

把一段文字变成一串数字（比如 384 个），语义相近的文字，数字也接近：

```
"granularity"    → [0.12, -0.34, 0.88, ...]
"数据粒度"        → [0.11, -0.31, 0.85, ...]   ← 很接近
"面试技巧"        → [-0.55, 0.22, -0.12, ...]  ← 差很远
```

这个"接近"用余弦相似度计算，结果 0~1，越接近 1 越相关。

每条笔记写入时自动生成向量存到 SQLite，查看某条笔记时取出它的向量，和所有其他向量逐一比较，返回最相关的 top-5。用户零操作，关联自动建立。

## Context

Notes in NoteMaster have no automatic associations. A vocabulary entry "granularity" and a concept "data sharding" may cover the same knowledge but the system has no way to surface that connection.

The existing knowledge graph builds edges via AI synthesis — all highlights from a book are sent to the LLM in one prompt. This has two fundamental problems:
1. Token cost is high and easily exceeds the practical 20k-token context limit on the local model
2. It only covers Apple Books highlights; English entries, questions, and captured inbox items are never linked

Manual linking (Obsidian-style backlinks) was validated and rejected — it requires sustained discipline that is hard to maintain long-term.

## Decision

Generate a vector embedding for each note at write time using a local Python library (`sentence-transformers`). Store vectors in SQLite. Compute cosine similarity at query time to find related notes across all types (entries, concepts, questions).

## How it works

**Embeddings** map text to a fixed-length list of numbers (384 dimensions). Semantically similar texts produce numerically similar vectors:

```
"granularity"    → [0.12, -0.34, 0.88, ...]
"数据粒度"        → [0.11, -0.31, 0.85, ...]  ← close
"interview tips" → [-0.55, 0.22, -0.12, ...] ← far
```

Closeness is measured with cosine similarity (0–1). At query time: fetch the target vector, compute similarity against all stored vectors, return top-k.

## Data flow

```
Note created or updated
        ↓
Background task: sentence-transformers encodes text → float list (milliseconds)
        ↓
Stored in embeddings table in SQLite
        ↓
User views a note
        ↓
Fetch that note's vector, compute cosine similarity against all others
        ↓
Return top-5 related notes (cross-type: entry / concept / question)
```

## Schema

New table, no changes to existing tables:

```sql
CREATE TABLE embeddings (
    note_type  TEXT NOT NULL,   -- 'entry' | 'concept' | 'question'
    note_id    TEXT NOT NULL,
    vector     TEXT NOT NULL,   -- JSON-serialized float list
    updated_at TEXT NOT NULL,
    PRIMARY KEY (note_type, note_id)
);
```

## Implementation plan

**`notemaster/embeddings.py`** — new module, isolated from AI and DB layers:

```python
from sentence_transformers import SentenceTransformer

_model = None  # lazy-loaded on first call

def embed(text: str) -> list[float]:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model.encode(text).tolist()

def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
```

**`notemaster/db.py`** — two new methods:

- `save_embedding(note_type, note_id, vector)` — upsert vector
- `get_related(note_type, note_id, limit=5)` — load all vectors, compute similarity, return top-k excluding self

**`notemaster/main.py`** — two changes:

- After creating/updating an entry or concept, add a background task `_bg_embed(note_type, note_id, text, db)`
- New endpoint: `GET /notes/{note_type}/{note_id}/related?limit=5`

**`frontend/index.html`** — "Related" collapsible section on entry and concept detail views, calls `/related`, shows top-3 with type label and title.

## Model

`all-MiniLM-L6-v2` via `sentence-transformers`:
- Size: ~80 MB (downloaded once to `~/.cache/huggingface/`)
- Dimensions: 384
- Inference: a few milliseconds per note on Apple Silicon (MPS)
- Language: multilingual support — handles Chinese and English in the same embedding space

No server required. Runs entirely in-process alongside FastAPI.

## Scale reasoning

At the expected data volume:

| Notes | Vector storage | Query time |
|-------|---------------|------------|
| 300   | ~460 KB       | ~0.1 ms    |
| 3,000 | ~4.6 MB       | ~1 ms      |
| 30,000| ~46 MB        | ~10 ms     |

Plain Python cosine similarity loop is sufficient up to tens of thousands of notes. FAISS or sqlite-vec would only be needed beyond that — well outside foreseeable use for a personal tool.

## Relationship to existing knowledge graph

The explicit graph (concept nodes + typed edges from AI synthesis) is retained for the graph visualisation view and directed traversal queries (`depends_on`, `contrasts_with`, etc.). Embeddings complement it:

| | Knowledge graph | Embeddings |
|---|---|---|
| Build cost | High (AI synthesis, many tokens) | Near zero (local model, milliseconds) |
| Coverage | Apple Books highlights only | All note types |
| Relation type | Explicit, typed | Implicit, semantic similarity |
| Maintenance | Manual re-synthesis needed | Automatic on every write |
| Use case | Visualisation, traversal | "Related notes", question context |

## Consequences

- Adds `sentence-transformers` as a dependency (~80 MB model download on first run)
- Embeddings are language-agnostic — Chinese and English notes associate naturally
- Existing notes need a one-time backfill (a migration script generates embeddings for all existing entries/concepts/questions)
- The embedding quality is bounded by `all-MiniLM-L6-v2`; a larger model could be swapped in by changing one line

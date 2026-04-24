# 003 — Entry attributes stored as a single JSON column

**Status**: Accepted  
**Date**: 2026-04

## Context

English vocabulary entries need several attributes: IPA phonetics, Chinese translation, usage note, example sentences, and optional extended fields (tenses, word forms, root, synonyms, derivatives). The initial schema had these as flat columns. As the number of optional fields grew, schema migrations became painful.

## Decision

Collapse all content attributes into a single `data TEXT` column storing a JSON object, mapped to a `EntryData` Pydantic model. The DB schema for `entries` is stable regardless of how many fields `EntryData` gains.

```sql
data TEXT NOT NULL DEFAULT '{}'
```

```python
class EntryData(BaseModel):
    phonetics: Optional[str] = None
    translation: Optional[str] = None
    context_note: Optional[str] = None
    examples: list[str] = []
    tenses: list[str] = []
    word_forms: list[str] = []
    root: Optional[str] = None
    synonyms: list[str] = []
    derivatives: list[str] = []
```

Partial updates use `model_dump(exclude_unset=True)` merged into the existing JSON, preserving fields not mentioned in the update.

## Reasoning

- Adding a new optional field requires no migration — just add it to `EntryData` with a default
- The field set is owned by the application layer (Pydantic), not by the database schema
- SQLite's `JSON_EXTRACT` can still query individual fields if needed

## Consequences

- Fields inside `data` are not individually indexed — full-text search or filtering by a specific field requires a table scan or a generated column
- The migration script (`scripts/migrate_entries_data.py`) was written to pack existing flat columns into JSON for the one-time upgrade

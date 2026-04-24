# 001 — SQLite, local-first architecture

**Status**: Accepted  
**Date**: 2026-04

## Context

The system stores personal study data: highlights, concepts, review history, job applications, English vocabulary. Options considered were a hosted database (PostgreSQL on a server or cloud), or a local SQLite file.

## Decision

Use SQLite on the local Mac, with the database file at `data/notemaster.db` (gitignored).

## Reasoning

- Zero infrastructure to run or pay for
- All data stays on the user's machine — no privacy concerns
- Single-file backup (`cp data/notemaster.db ~/backup/`)
- SQLite handles the expected data volume (thousands of notes, tens of thousands of review records) without any tuning
- Consistent with the self-hosted AI philosophy of the project

## Consequences

- Multi-device sync is not supported (acceptable for a personal tool used on one Mac)
- If the database file is deleted, all data is lost — no remote backup by default
- SQLite bottleneck is estimated around 100k–1M rows for this access pattern, well beyond foreseeable use

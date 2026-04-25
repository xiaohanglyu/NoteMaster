# Architecture Decision Records

Key decisions made during development, with context and tradeoffs.

| # | Decision | Status |
|---|----------|--------|
| [001](001-sqlite-local-first.md) | SQLite, local-first architecture | Accepted |
| [002](002-self-hosted-ai.md) | Self-hosted AI via OpenAI-compatible API | Accepted |
| [003](003-entry-json-data-column.md) | Entry attributes as single JSON column | Accepted |
| [004](004-knowledge-graph-synthesis.md) | Knowledge graph built by AI synthesis | Accepted, under review |
| [005](005-single-file-pwa.md) | Single-file PWA frontend, no build step | Accepted |
| [006](006-tdd-methodology.md) | Test-driven development | Accepted |
| [007](007-vector-embeddings-association.md) | Lightweight knowledge association via vector embeddings | Accepted |

## How to add a new ADR

Copy this template into a new numbered file:

```markdown
# NNN — Title

**Status**: Proposed / Accepted / Deprecated  
**Date**: YYYY-MM

## Context
What problem are we solving, and what options existed?

## Decision
What did we choose?

## Reasoning
Why this option over the alternatives?

## Consequences
What are the tradeoffs? What does this make harder?
```

Status can be updated over time — mark old decisions as `Deprecated` rather than deleting them.

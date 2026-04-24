# 004 — Knowledge graph built by AI synthesis, not manual linking

**Status**: Accepted, under review  
**Date**: 2026-04

## Context

The system needs to associate notes with each other for review prioritisation, question generation context, and visualisation. Two approaches were considered: manual linking (Obsidian-style backlinks) or AI-generated graph edges.

## Decision

Use AI synthesis: send all highlights from a book to the LLM in one prompt, which extracts concept nodes and directed edges with typed relations (`depends_on`, `contrasts_with`, `part_of`, `example_of`).

## Reasoning

- Manual linking requires sustained discipline that is hard to maintain long-term (validated by prior Obsidian usage — links accumulate initially then stagnate)
- AI-generated edges require zero ongoing effort from the user
- Typed relations add semantic value for traversal queries and graph visualisation

## Consequences

- **Token cost is high**: the synthesis prompt bundles all highlights, easily exceeding the practical 20k-token context limit on the local model (tracked in issue #36)
- Synthesis quality degrades for large books with many highlights
- The graph is a snapshot — it does not automatically update when highlights change

## Under review

Considering a complementary approach based on vector embeddings:
- Embed each note at write time (fast, cheap, automatic)
- Use cosine similarity for "related notes" retrieval instead of graph traversal
- The explicit graph would be retained for visualisation and typed relations, but would no longer be the only path for content association

See issue #36 and the discussion on lightweight alternatives.

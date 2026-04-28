# 008 — NoteMaster is a learning coach, not a knowledge base

**Status**: Accepted  
**Date**: 2026-04

## Decision

NoteMaster's identity is a **personal learning coach** — an execution and practice layer — not a knowledge management system or second brain.

## Context

During product design discussions, the scope kept expanding: knowledge graph, note-taking, concept wiki, Obsidian integration, LLM-powered knowledge extraction. The discovery of tools like [LLM Wiki](https://github.com/nashsu/llm_wiki) (which auto-transforms documents into an interconnected wiki with graph visualization and semantic search) forced a clear question: should NoteMaster compete in that space?

The answer is no.

## The distinction

| Tool type | Job | Examples |
|-----------|-----|---------|
| Knowledge base | Store, link, retrieve knowledge | Obsidian, Notion, LLM Wiki |
| Learning coach | Tell you what to practice, make you do reps, track improvement | **NoteMaster** |

A second brain is **passive** — you put knowledge in, you retrieve it when needed.  
A coach is **active** — it schedules your training, pushes you through drills, measures your progress.

## Architecture consequence

NoteMaster is the coordinator. Knowledge lives elsewhere.

```
Data Sources (plug in what you use)
├── NoteMaster DB       — English vocab, questions, job tracking, review state
├── Obsidian / LLM Wiki — Knowledge graphs and notes (user's choice)
├── Hello Interview     — SD/LLD curriculum
├── NeetCode            — Coding problem list
└── Web / articles      — On-demand content ingestion
         ↓
    NoteMaster
    ↓           ↓           ↓
Daily plan   Practice   Progress
```

NoteMaster stores **learning state** (what you've practiced, SM-2 intervals, scores, job progress) — not knowledge itself.

## What this means for existing features

| Feature | Verdict | Reason |
|---------|---------|--------|
| Concepts / knowledge graph | Deprioritise | LLM Wiki and Obsidian do this better |
| Apple Books synthesis | Keep light | Source for English + question practice, not general knowledge |
| Inbox routing | Keep | Routes to practice queues, not to a knowledge base |
| English entries | Keep | Spaced repetition state is NoteMaster's unique value |
| Interview questions | Keep | Practice + SM-2 scheduling is NoteMaster's unique value |
| Job Kanban | Keep | Execution tracking, not knowledge |
| Daily plan | Build next | The clearest expression of the coach identity |

## Why not LLM Wiki inside NoteMaster

LLM Wiki's two-step chain-of-thought extraction and Louvain community detection are impressive, but:

1. Rebuilding this inside NoteMaster duplicates a tool that already exists and does it better
2. It pulls NoteMaster toward knowledge storage, away from coaching
3. The better integration is: user runs LLM Wiki or Obsidian for knowledge, NoteMaster reads from it as a datasource

The one idea worth borrowing is the **two-step extraction approach** for improving the "From Article → Questions" feature quality — not to build a wiki, but to generate better practice material.

## Rejected alternatives

**"Build a full knowledge wiki inside NoteMaster"** — rejected. NoteMaster is not a better Obsidian. Competing there dilutes focus and duplicates tools the user already has.

**"Make Obsidian the required knowledge store"** — rejected. Obsidian is one datasource option among many. NoteMaster must work standalone without any external tool.

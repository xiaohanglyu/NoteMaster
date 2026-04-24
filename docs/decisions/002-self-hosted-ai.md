# 002 — Self-hosted AI (local llama.cpp / Ollama)

**Status**: Accepted  
**Date**: 2026-04

## Context

The system uses AI for concept synthesis, entry enrichment, answer evaluation, and inbox classification. Options were a cloud API (OpenAI, Anthropic) or a self-hosted local model.

## Decision

Use a self-hosted model via an OpenAI-compatible API endpoint (currently Gemma 4 26B on a local server at `192.168.1.81:8080`). The client code uses the `openai` Python SDK pointed at the local base URL.

## Reasoning

- No API costs — the system runs sessions and enrichment without accumulating charges
- Data privacy — highlights, personal notes, and job application details never leave the local network
- The OpenAI-compatible interface means switching models or providers requires only a `.env` change

## Consequences

- AI response quality is bounded by the local model's capability (currently Gemma 4 26B)
- Practical context limit is ~20k tokens due to network latency and timeout constraints, not model context window
- Long-running AI tasks (full-book synthesis) can time out — mitigated by chunked processing (see issue #36)
- If the local server is down, all AI features are unavailable (fail silently in background tasks)

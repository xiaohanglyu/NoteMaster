# 006 — Test-driven development (tests first, always)

**Status**: Accepted  
**Date**: 2026-04

## Context

The codebase covers multiple interacting layers: Pydantic models, SQLite CRUD, AI prompts, and FastAPI endpoints. Without tests, regressions are caught late and refactoring is risky.

## Decision

Every new behaviour is written as a failing test before any implementation. The test suite (`tests/unit/`) uses only in-memory SQLite and mocked AI clients — no external dependencies, so it runs anywhere in under a minute.

## Reasoning

- Regressions are caught immediately, not after manual testing
- The test suite documents the intended interface of every module
- Mocking AI clients and using `:memory:` SQLite makes the suite fast and deterministic
- The discipline of writing the test first forces clarity about what the code should actually do

## Consequences

- Writing tests for every feature adds upfront time (approximately 30–50% overhead per feature)
- AI prompt quality and model behaviour cannot be unit-tested — integration tests exist separately but are run manually
- The frontend (single-file HTML/JS) is not unit-tested; feature correctness requires manual browser verification

# ADR 010 — AnkiConnect Export

**Date:** 2026-05-01  
**Status:** Accepted

---

## Context

NoteMaster entries (vocabulary, phrases, expressions) accumulate spaced-repetition data but live in isolation from Anki, which many users already run as their primary flashcard system. Users want to selectively push enriched entries into Anki without losing formatting or having to manually recreate cards.

Three export mechanisms were considered:

| Option | Implementation | Pros | Cons |
|--------|---------------|------|------|
| CSV/TSV | Backend endpoint | Simple, universal | No styling, manual import, no dedup |
| APKG (genanki) | Backend, Python lib | Styled cards, self-contained | Extra dependency, file download dance |
| **AnkiConnect** | Frontend JS → localhost:8765 | Live push, dedup, deck/model selection | Anki must be open |

AnkiConnect is the best fit for a local-first workflow: the user already has Anki open when studying, push is instant, and Anki handles deduplication by note key automatically.

---

## Decision

Implement Anki export as a **frontend-only feature** that calls AnkiConnect directly from the browser. No backend changes are required beyond the already-added `POST /shadow` generic endpoint.

### Architecture

```
Browser (NoteMaster)
  │
  ├─ fetch entries via /entries (existing)
  │
  └─ POST http://localhost:8765  (AnkiConnect)
       ├─ deckNames / createDeck
       ├─ modelNames / modelFieldNames / createModel
       └─ addNotes (with duplicate policy = "ignore")
```

### User flow

1. User filters entries by tag or search, checks desired cards
2. Floating action bar shows: `N selected · M ✓ ready · K ⚠ missing fields`
3. User clicks **Push to Anki** → modal opens
4. Modal fetches deck list and model list from AnkiConnect
5. User selects (or names) a deck; selects a note type
   - Default: "NoteMaster" model (auto-created if absent)
   - Existing model: field mapping UI appears
6. Confirm → push → result summary

### Sync readiness

An entry is **ready** (`✓`) if it has `phonetics` AND `translation`. Entries missing these fields are flagged `⚠` as a hint — push is not blocked.

### NoteMaster default Note Type

When "NoteMaster (auto-create)" is selected, the model is created with:

| Field | Source |
|-------|--------|
| Word | `entry.text` |
| Phonetics | `data.phonetics` |
| Translation | `data.translation` |
| Examples | `data.examples.join("<br>")` |
| Notes | `data.context_note` |
| Context | `entry.source_ref` |

Card template: Front = Word; Back = all fields stacked with minimal HTML styling.

### Field mapping for existing Note Types

When an existing model is chosen, `modelFieldNames` is called and a dropdown mapping is shown for each NoteMaster field. Unmapped fields are skipped. At minimum, Word → some field must be mapped.

---

## Consequences

- No backend changes needed (pure frontend feature)
- User must have Anki open with AnkiConnect addon installed (code `2055492159`)
- AnkiConnect CORS must allow the NoteMaster origin (`http://localhost:*`) — one-time config
- Duplicate notes are silently skipped by Anki (`duplicateScope: "deck"`)

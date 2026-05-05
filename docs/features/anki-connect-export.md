# AnkiConnect Export

## Why

NoteMaster entries live in isolation from Anki. Users want to push selected, enriched vocabulary cards into their existing Anki decks without manual copy-paste or file juggling.

## Prerequisites (user setup, one-time)

1. Install AnkiConnect addon in Anki — code `2055492159`
2. In AnkiConnect config, add NoteMaster origin to `webCorsOriginList`:
   ```json
   { "webCorsOriginList": ["http://localhost:8000"] }
   ```
3. Restart Anki

---

## Design

Anki export is a low-frequency batch operation. It lives in **Admin**, not in the English study view (which stays focused on learning).

### Entry point

Admin → Anki Export section.

### Layout

```
┌─ Anki Export ──────────────────────────────────────────────────┐
│  [Tag: All ▾]  [Readiness: All ▾]  [Search: ________]          │
│                                                                  │
│  [☑ Select all]  47 matched · 42 ✓ ready · 5 ⚠ missing         │
│  ──────────────────────────────────────────────────────         │
│  ☑ ✓  jitter          /ˈdʒɪtər/   抖动；紧张感                 │
│  ☑ ✓  hit the ground… /hɪt…/      迅速投入工作                  │
│  ☐ ⚠  bootstrap       —           —                             │
│  ...                                                             │
│                                                                  │
│  23 selected  [Push to Anki ▶]                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Filter panel

| Control | Options | Default |
|---------|---------|---------|
| Tag | All · pronunciation · expression · vocabulary · phrase · interview | All |
| Readiness | All · Ready only (✓) · Missing fields (⚠) | All |
| Search | free text, matches word text | empty |

Filters are applied client-side against the already-loaded entry list.

### Entry list

- Each row: `checkbox · readiness badge · word · phonetics · translation`
- Readiness: `✓` = has phonetics + translation; `⚠` = missing one or both
- Checkboxes are always visible (not hover-dependent)
- **Select all** selects all currently filtered entries (not all 191 total)
- Individual rows can be toggled independently

### Summary bar (below list)

```
N selected · M ✓ ready · K ⚠ missing  [Push to Anki]
```

Push button is always enabled — ⚠ entries push anyway, badge is informational.

### Push modal

Unchanged from previous design — deck selector, model selector, field mapping, result banner. See Components 3–5 in the original spec.

---

## Components

### 1. `isEntryReady(entry)` — pure function
Returns `true` if `data.phonetics && data.translation`.  
Used in both the export list rows and the summary count.

### 2. `ankiConnect(action, params)` — client
```js
async function ankiConnect(action, params = {}) {
  const resp = await fetch("http://localhost:8765", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, version: 6, params }),
  });
  const data = await resp.json();
  if (data.error) throw new Error(data.error);
  return data.result;
}
```

### 3. `buildNote(entry, deckName, modelName, fieldMap)` — pure function
Maps an Entry to an AnkiConnect note payload.  
`fieldMap = null` → use NoteMaster default fields.  
`fieldMap = { word, phonetics, … }` → custom mapping, skips empty values.

### 4. Push modal
Deck selector, model selector (NoteMaster auto-create default), field mapping for custom models, result banner.

### 5. NoteMaster default Note Type

| Field | Source |
|-------|--------|
| Word | `entry.text` |
| Phonetics | `data.phonetics` |
| Translation | `data.translation` |
| Examples | `data.examples.join("<br>")` |
| Notes | `data.context_note` |
| Context | `entry.source_ref` |

---

## What is NOT in the English view

- No hover checkboxes for Anki sync
- No sync badge on entry cards
- No "Push to Anki" in the bulk toolbar
- The existing bulk toolbar remains for AI expand only

---

## Issues

| # | Title |
|---|-------|
| #63 | feat: Admin — Anki Export filter + entry list + select all |
| #64 | feat: Admin — wire push flow into Anki Export section |
| #65 | chore: clean up English view — remove Anki sync UI |

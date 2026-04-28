# Pronunciation Practice

## Why

Practicing LeetCode and system design answers in English requires more than knowing the content — delivery matters in real interviews. This feature lets you record yourself answering a question and get immediate feedback on which words were mispronounced or unclear.

## Architecture: pluggable backends

Pronunciation scoring is abstracted behind a `PronunciationBackend` interface so the engine can be swapped without touching the UI or API. Two backends are planned:

| Backend | Mechanism | Granularity | Offline | Issue |
|---------|-----------|-------------|---------|-------|
| **Level 1 — Whisper** | Word-match via transcription diff | Word | Yes | #44 |
| **Level 2 — Azure** | Phoneme-level acoustic model | Phoneme + prosody | No | #45 |

The active backend is selectable from Admin → Settings (same pattern as AI providers).

---

## Level 1 — Whisper word-match (implemented first)

### How it works

```
User records audio
      ↓
mlx-whisper transcribes → word list + token log-probabilities
      ↓
Diff against reference text (expected answer)
      ↓
Classify each word: matched / substituted / omitted / inserted
      ↓
LLM generates feedback on top problem words
```

### Scoring

- **Word accuracy** = matched words / total reference words (0–100%)
- Per-word status: `ok` / `substituted` / `omitted` / `inserted`
- Low log-probability words flagged even when transcription matches (uncertain pronunciation)
- LLM feedback targets top 3–5 problem words with specific advice

### Limitations

- Detects the wrong word, not the wrong phoneme — saying a synonym counts as an error
- No fluency or prosody scoring
- Heavily accented but intelligible speech may score low unfairly

These are known trade-offs accepted for Level 1. Level 2 addresses them.

---

## Level 2 — Azure Pronunciation Assessment (upgrade path)

Azure Cognitive Services returns structured JSON with:
- Word accuracy scores (0–100)
- Per-phoneme confidence
- Error type classification: `Omission` / `Insertion` / `Mispronunciation`
- Fluency score (pace and hesitations)
- Completeness score

Requires `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION` in `.env`. When configured, the same UI automatically shows phoneme-level highlights instead of word-level.

---

## Practice modes

### Shadow reading
Reference answer is shown on screen. User reads it aloud. Scored against the exact reference text — best for drilling specific vocabulary and technical terms (`concurrency`, `idempotent`, `eventual consistency`).

### Free answer
Question shown, reference answer hidden. User speaks their own answer. Two scores returned:
1. **Content score** — LLM evaluates whether key concepts were covered
2. **Pronunciation score** — same word-match or Azure pipeline

Shadow reading is implemented first; free answer comes after.

---

## UI flow

```
Question card → "Practice Speaking" button
      ↓
Practice panel opens (reference text shown for shadow mode)
      ↓
Record button → audio captured in browser
      ↓
POST /questions/{id}/pronounce  { audio, mode }
      ↓
Results: overall score + per-word highlights + LLM feedback
      ↓
"Try again" or "Next question"
```

---

## API

```
POST /questions/{id}/pronounce
Body: multipart — audio (webm/wav), mode (shadow|free)
Response:
{
  "overall_score": 82,
  "words": [
    {"word": "concurrency", "status": "substituted", "heard": "con-currency", "score": 45},
    ...
  ],
  "feedback": "Your main issues: 'idempotent' (missed the second syllable), 'throughput' (try THRU-put not through-PUT).",
  "backend": "whisper"
}
```

---

## Implementation order

1. `PronunciationBackend` interface + `WhisperBackend` in `notemaster/pronunciation.py`
2. `POST /questions/{id}/pronounce` endpoint
3. Frontend: record button + results panel on question card
4. Tests: mock backend for API tests, real Whisper for integration

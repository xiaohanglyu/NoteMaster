# Feature: Article → Questions

**Issue**: #39  
**Status**: In development

---

## Problem

Reading articles, system design guides, and tech blogs is passive. There is no
mechanism to verify that you have actually internalized the material or can
articulate it under the pressure of a real interview.

Manual question creation is tedious and inconsistent. The goal of this feature
is to turn any article — a URL, a pasted Markdown document, or a PDF — into a
set of targeted practice questions in seconds.

---

## User story

> As an engineer preparing for system design interviews, I paste a link to a
> system design guide. NoteMaster fetches the article, reads it, and generates
> two sets of questions: one to build understanding and one to simulate an
> interviewer grilling me. Both sets land in my question bank and are
> immediately available for drill and spaced repetition.

---

## Two modes

### Study mode

Goal: verify comprehension and build the mental model.

Each question targets one of three angles:

| Angle | Example |
|-------|---------|
| Definition | "What is rate limiting, and why is it needed at an API gateway?" |
| Comparison | "What are the tradeoffs between token bucket and leaky bucket algorithms?" |
| When to use | "In what situation would you prefer eventual consistency over strong consistency?" |

- Full model answers are included — read and absorb, not just a prompt.
- Questions are tagged `study` and the source URL/filename.
- Quantity: 5–8 questions per article.

### Interview mode

Goal: simulate interview pressure; force production of coherent English.

Each question is scenario-based:

> "You are designing a public REST API for a fintech startup. The product team
> wants to add a new field to an existing response object. How do you handle
> versioning, and what are the tradeoffs of your chosen strategy?"

Additional properties per question:

- **follow_ups**: 2–3 probing follow-up questions pre-generated alongside the
  main question, stored in the `notes` field as JSON. These represent what a
  senior interviewer would ask after an adequate initial answer.
  ```json
  ["Why not use URL versioning here?",
   "How does your strategy behave when the client is a mobile app that can't be force-updated?",
   "What breaks in your design if two teams need to evolve the same endpoint independently?"]
  ```
- **q_type**: inferred from the article topic (`system_design`, `coding`, `other`).
- Answer is a 3–5 sentence, interview-quality English model answer.
- Questions are tagged `interview` and the source URL/filename.
- Quantity: 5–8 questions per article.

---

## Input formats

| Format | How it works |
|--------|-------------|
| URL | Backend fetches the page with `httpx`, strips HTML with `BeautifulSoup`, feeds plain text to the AI |
| Markdown / plain text | Pasted directly into the text area, no fetch needed |
| PDF | Reuses the existing `pypdf` importer already in `importer.py` |

Text is trimmed to a safe limit (~12 000 characters) before sending to the AI
to stay within the local model's practical context window (see
[ADR 002](../decisions/002-self-hosted-ai.md)).

---

## Data model

No new tables or columns. Questions are stored as `InterviewQuestion` with:

| Field | Value |
|-------|-------|
| `source` | `QuestionSource.MOCK` (generated, not from a real interview) |
| `q_type` | inferred by AI |
| `tags` | `["article", "study"]` or `["article", "interview"]`, plus source slug |
| `notes` | for interview mode: JSON array of follow-up strings |

---

## API

```
POST /articles/generate-questions
```

Request body:
```json
{
  "url": "https://example.com/system-design-guide",   // optional
  "content": "# API Design\n...",                      // optional (one of url/content required)
  "mode": "study | interview",                         // default: "study"
  "count": 6                                           // default: 6, max: 10
}
```

Response:
```json
{
  "questions_created": 6,
  "question_ids": ["q-abc1", "q-abc2", "..."],
  "source_title": "API Design — Hello Interview"
}
```

The endpoint is synchronous — it blocks while the AI generates. For a typical
article this takes 10–30 seconds on a local model. A loading state is shown in
the UI.

---

## Frontend

Location: **Questions** view → "From Article" button in the header.

```
[ From Article ]  ← new button alongside existing "+ Add Question"
```

Opens a panel with:

1. **Source input** — URL field or "Paste text" textarea (tabs)
2. **Mode selector** — Study / Interview toggle
3. **Count** — slider 4–10 (default 6)
4. **Generate** button → spinner while waiting
5. **Preview list** — generated questions shown before saving, with inline
   edit for any question or answer
6. **Save all** button → POST to API, close panel, refresh question list

---

## AI prompts

### Study mode prompt (system)

```
You are an expert technical interviewer and educator.

Read the article below and generate {count} review questions that cover the
key concepts. Each question must target ONE of these angles (mix them):
- Definition: "What is X and why does it exist?"
- Comparison: "What are the tradeoffs between X and Y?"
- When-to-use: "In what situation would you choose X over Y?"

For each question, write a complete, clear answer (3–5 sentences).

Classify each question as: system_design | coding | other

Respond ONLY with a JSON array:
[{"question":"...","answer":"...","q_type":"..."}]
```

### Interview mode prompt (system)

```
You are a senior staff engineer conducting a technical interview.
Your style: probing, scenario-based, never abstract.

Read the article below and generate {count} interview questions.
Rules:
- Frame each question as a real scenario ("You are designing / You're on-call / Your team needs...")
- Write a model answer: 3–5 sentences, interview-quality English, concise and precise
- Write 2–3 follow-up probes an interviewer would ask after a good initial answer
- Classify as: system_design | coding | other

Respond ONLY with a JSON array:
[{"question":"...","answer":"...","q_type":"...","follow_ups":["...","..."]}]
```

---

## Testing strategy

All tests are unit tests with mocked AI client and mocked `httpx` responses.

| File | What it covers |
|------|---------------|
| `tests/unit/test_article_ai.py` | `generate_questions_from_article()` — both modes, follow_ups, JSON fence stripping, invalid JSON error |
| `tests/unit/test_article_api.py` | POST endpoint — URL input, text input, mode param, questions saved to DB, response shape |

No integration tests: URL fetching is mocked in unit tests. A real URL can be
tested manually via the UI.

---

## Acceptance criteria

- [ ] URL input: article is fetched and text extracted server-side
- [ ] Text input: raw markdown/text is used directly
- [ ] Study mode: ≥ 5 questions generated with answers, tagged `study`
- [ ] Interview mode: ≥ 5 questions with answers + follow_ups stored in `notes`, tagged `interview`
- [ ] All questions appear in the question bank immediately after generation
- [ ] Full unit test suite stays green
- [ ] UI: preview before save, inline edit, mode toggle

---

## Out of scope (this iteration)

- Streaming the generated questions one-by-one as the AI produces them
- Deduplication against existing questions
- Linking generated questions to concept nodes automatically
- Re-generating questions from the same URL (no URL storage)

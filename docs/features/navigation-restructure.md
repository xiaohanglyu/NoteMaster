# Feature: Navigation Restructure & Question Category Split

**Status**: In development  
**Related issues**: #37 (nav redesign), #40 (question category split)

---

## Why we're doing this

NoteMaster has grown to cover three distinct workflows that have fundamentally
different rhythms and goals:

| Domain | Frequency | Input sources | Goal |
|--------|-----------|--------------|------|
| English | Daily micro-practice | Capture, manual | Fluent expression |
| Tech | Episodic deep work | Articles, books, URLs | Mastery of knowledge |
| Job | Intensive during job search | Interview logs, Capture | Get the offer |

The current navigation treats these three as flat peers, but they are used in
completely different contexts. More critically, **interview questions** appear
in both Tech (study questions from articles) and Job (questions from real
interviews), and right now they land in the same view with no distinction.

This causes two problems:
1. The Questions view is cluttered — behavioral stories and article-generated
   system design study questions sit next to each other with no separation.
2. "From Article" (issue #39) has no clear home — it doesn't belong in a
   job-application context.

---

## The core insight: two kinds of questions

Both Tech and Job use Q&A pairs, but they are different in nature:

**Study questions** (`category: study`)
- Generated from articles, books, or concept notes
- Evergreen — not tied to any company or round
- Goal: "Can I explain this concept?"
- Live in the **Tech / Learn** context

**Interview questions** (`category: interview`)
- Tied to a company, round, or real interview experience
- Contextual — used during active job search
- Goal: "Can I perform under pressure?"
- Live in the **Job** context

The user should never have to choose the category manually. It is inferred from
context: generated from an article → study; recorded from an interview → interview.

---

## Two-phase plan

### Phase 1 — Data model + view separation (this document)

Add `category: study | interview` to `InterviewQuestion`.

- Default all existing questions to `category: interview` (backward compatible)
- Article-generated questions default to `category: study`
- Tech view shows only `study` questions
- Job / Questions view shows only `interview` questions
- "From Article" moves to Tech view

This is a purely additive change — no data loss, no breaking API changes.

### Phase 2 — Full navigation redesign (follow-up, issue #37)

Once all features are stable, restructure top-level navigation into three
sections:

**Learn** (Tech)
- Concept notes (from books, AI synthesis, manual)
- Articles & URLs → study question generation
- Knowledge mastery testing (SM-2 on concepts + study questions)

**Practice**
- Daily review session across all types (current Session)
- English drill
- Tech study question drill
- Mock interview simulation

**Hunt** (Job)
- Application Kanban
- Company-specific interview questions & STAR stories
- Round preparation — linked questions per round

**Capture** remains a universal inbox routing to any of the three domains.

Phase 2 is deferred until the feature set stabilises. Phase 1 can ship
independently without any UI restructuring.

---

## Phase 1 implementation details

### Model change

```python
class QuestionCategory(str, Enum):
    STUDY = "study"
    INTERVIEW = "interview"

class InterviewQuestion(BaseModel):
    ...
    category: QuestionCategory = QuestionCategory.INTERVIEW
```

### DB migration

`ALTER TABLE interview_questions ADD COLUMN category TEXT NOT NULL DEFAULT 'interview'`

Run automatically in `_create_tables()` via `ADD COLUMN IF NOT EXISTS`.

### API changes

- `GET /questions` accepts optional `?category=study|interview`
- `POST /articles/generate-questions` sets `category=study` on all created questions
- `POST /questions` defaults to `category=interview` unless specified

### Frontend changes

- Questions view: filter to `category=interview` by default (add `?category=interview` to fetch)
- New "Study Questions" section in Tech view (or temporarily an entry in Admin): filter to `category=study`
- "From Article" button moves from Questions view to the Study Questions entry point

### No breaking changes

Existing questions gain `category=interview` by default. All current behaviour
is preserved. The Questions view simply gains a pre-applied filter.

---

## Acceptance criteria (Phase 1)

- [ ] `QuestionCategory` enum added to models
- [ ] `category` column added to `interview_questions` table
- [ ] `GET /questions?category=` filter works
- [ ] Existing questions default to `interview`
- [ ] Article-generated questions default to `study`
- [ ] Questions view shows only `interview` questions
- [ ] Study questions accessible from a separate entry point
- [ ] Full test suite stays green

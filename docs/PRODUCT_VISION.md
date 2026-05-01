# NoteMaster — Product Vision

> From tool chest to coaching system.

---

## The Problem With the Current State

NoteMaster has solid data layers and individual features, but no coherent feedback loop. The user has to:
- Decide what to practice
- Figure out on their own if they're improving
- Connect dots across English, SD, Behavioral, Coding manually

The SM-2 scheduling is correct but SM-2 alone is not coaching. **A tool chest is not a coach.**

---

## The New Identity

NoteMaster is a **personal interview and English coach** that:

1. Knows where you are weak
2. Tells you what to practice today and why
3. Evaluates your answers in real time
4. Summarizes what you learned and what to fix next

---

## The Three AI Roles

### 1. Content Creator (async, one-time)
Runs in the background. User does not wait.
- Generate questions from articles
- Extract `key_points` from ideal answers
- Generate Hello Interview-style SD sections
- Auto-enrich English entries (phonetics, translation, examples)

### 2. Real-time Evaluator (per practice session, seconds)
Triggered after every answer or recording.
- **Answer coverage**: which key_points were hit ✓, which were missed ✗
- **English expression**: flag unnatural sentences, suggest better phrasing
- **Pronunciation**: word-level scoring, flag mispronounced words
- Uses local/fast model to avoid breaking practice flow

### 3. Coach (per session + daily, can be slower)
Synthesizes history into actionable guidance.
- Post-answer: "You covered scaling but always miss consistency — focus there next time"
- Post-session: "Today: 3 SD questions, HLD improved, database tradeoffs still weak"
- Daily plan: "Google interview in 5 days. Today: 30min SD, 15min pronunciation"

---

## AI Roles by Module

| Module | Creator | Evaluator | Coach |
|--------|---------|-----------|-------|
| English vocab | Auto-enrich entries | Pronunciation score, expression feedback | Pronunciation trends, which words to drill |
| Concepts | Synthesize from highlights | Check explanation accuracy | Light — SM-2 sufficient |
| Questions / Problems | Generate questions, key_points, sub-questions | Answer coverage, English quality | Per-answer feedback, pattern recognition |
| Inbox | — | Classify items | — |
| Job Hunt | Generate company-specific prep questions | — | Interview countdown drives all priorities |

**Key principle**: The Job Hunt module is the **priority controller** for the entire system. An upcoming interview shifts all module planning toward that goal.

---

## Goals System (CoachGoal)

The user can have **multiple concurrent goals**. Each goal shapes the daily plan.

```
CoachGoal
  ├── title          "Google SD Interview" / "Improve Pronunciation" / "Finish Blind 75"
  ├── goal_type      interview | skill | curriculum
  ├── ref_id         → application_id, problem_type, or null
  ├── deadline       Optional date
  ├── priority       1–3 (manual)
  └── daily_minutes  time budget per day
```

Daily plan allocation = **deadline urgency × priority × remaining time budget**.

When no deadline exists, SM-2 and priority fill the remaining time.

**Automatic source**: Interview rounds in the Job Hunt module with scheduled dates are automatically read as goals — no manual entry required.

---

## Interview Question: Richer Data Model

Every `InterviewQuestion` gains:

```
InterviewQuestion
  ├── self_score: int (0–3)     user's own mastery rating — this IS the "level"
  ├── key_points: [{text}]      AI-extracted rubric items, stored as JSON
  └── sub_questions: [{text, answer, self_score}]   follow-ups, each rated independently
```

`self_score` represents mastery, not difficulty. The user rates themselves after each attempt. SM-2 uses this to schedule the next review.

---

## Answer History (QuestionAttempt)

Every practice attempt is saved:

```
QuestionAttempt
  ├── question_id
  ├── response_text       transcribed speech or typed answer
  ├── coverage            [{point, hit: bool}]   key_points coverage
  ├── ai_feedback         English expression feedback
  ├── score               float 0–1
  └── attempted_at
```

The user can see all past attempts on a question, track improvement over time, and compare what they said vs what they should have said.

---

## Error Notebook (错题本)

Mistakes during practice flow automatically into the English vocabulary (Entry) system.

**Two entry points:**
1. Shadow reading — words with pronunciation score < threshold → one-click or auto add to Entry
2. AI expression feedback — flagged sentences/words → one-click add to Entry

**Auto-applied system tags:**

| Source | Tag |
|--------|-----|
| Low pronunciation score | `pronunciation` |
| AI expression flag | `expression` |
| Manual new word | `vocabulary` |
| Multi-word phrase | `phrase` |
| From interview question | `interview` |

`Entry.source_ref` points back to the originating question. Context is preserved for review.

---

## Practice Flow (per question)

1. Open question → see **key_points as a structured outline** (answer framework)
2. Record or type answer
3. AI returns immediately:
   - Coverage: key_points ✓ / ✗ with brief explanation
   - Expression: specific sentences flagged with better alternatives
4. User rates self (0–3) → SM-2 schedules next review
5. Wrong words/phrases → one-click add to Entry with tag
6. Attempt saved to QuestionAttempt history

---

## Coach Dashboard (Home)

The home page is no longer a task list. It is a coaching brief:

```
TODAY'S FOCUS
  Google SD Interview — 5 days left

PRACTICE PLAN
  ☐ System Design × 1     (URL Shortener — last score: 2, scaling weak)
  ☐ Behavioral × 2        (STAR structure inconsistent)
  ☐ Pronunciation × 10    (words due from 错题本)

YOUR WEEK
  SD: improving ↑   Behavioral: stalled →   Pronunciation: 3 new errors ↓

GOALS
  [+ Add Goal]   Google SD (5d) · Blind75 (3w) · Pronunciation (ongoing)
```

---

## Content Management Principle

**Every feature that creates data must ship with a management interface.**

- `key_points` — inline edit on question card
- `sub_questions` — inline add/edit/delete, individual self_score
- `QuestionAttempt` — history list per question, deletable
- `CoachGoal` — full CRUD on home page
- `Entry` tags — filterable by system tags + custom tags

No feature ships without its admin UI.

---

## AI Tone

No character names. Tone varies by context:

- **Evaluator** — direct, like an examiner:
  > "Covered 3/5 key points. Missing: consistency model, failover strategy."

- **Coach** — explanatory, with reason:
  > "Focus on SD today. Google interview in 5 days. Last attempt on scaling scored 1/3."

Professional, not a toy.

---

## Implementation Priority

1. `CoachGoal` model + DB + API + Home UI
2. `key_points` + `sub_questions` on InterviewQuestion — data layer + inline management
3. `QuestionAttempt` — save history, view per question
4. Real-time evaluator — coverage check + expression feedback after answer
5. Error notebook — pronunciation + expression → Entry flow
6. Coach Dashboard — replace current Daily Plan with full coaching brief

# ADR 009 — Coaching System Redesign

**Date:** 2026-04-30  
**Status:** Accepted

---

## Context

NoteMaster has grown into a tool chest: English vocab, concepts, interview questions, SD problems, inbox, job hunt tracking. Each module works independently but there is no coherent feedback loop. The user must decide what to practice, figure out their own progress, and connect improvement dots across domains manually.

SM-2 schedules reviews correctly but SM-2 alone is not coaching. A coach diagnoses weaknesses, prescribes practice, evaluates performance, and summarises progress.

---

## Decision

Redesign NoteMaster around a **coaching loop**:

```
Goals → Daily Plan → Practice → AI Evaluation → History → Coach Summary → Goals
```

This requires six concrete additions:

### 1. CoachGoal — multi-goal priority system

Users declare one or more goals. Each goal drives daily plan allocation.

```
CoachGoal
  id, title, goal_type (interview|skill|curriculum),
  ref_id (→ application_id or problem_type),
  deadline (optional), priority (1–3), daily_minutes
```

Daily plan = deadline urgency × priority × SM-2 due items. When no goals exist, falls back to pure SM-2.

Interview rounds with scheduled dates in the Job Hunt module are **automatically surfaced** as implicit goals.

### 2. Richer InterviewQuestion — key_points + sub_questions

```
InterviewQuestion gains:
  key_points:     [{text}]                    JSON, AI-extracted rubric
  sub_questions:  [{text, answer, self_score}] JSON, follow-ups with individual mastery
```

`self_score` (0–3) is the user's mastery rating, not a difficulty level. SM-2 uses it for scheduling.

### 3. QuestionAttempt — answer history

Every practice attempt is persisted.

```
QuestionAttempt
  id, question_id, response_text, coverage [{point, hit}],
  ai_feedback, score, attempted_at
```

### 4. AI Evaluator — real-time coverage + expression feedback

After each answer (typed or transcribed):
- Coverage check: key_points ✓ / ✗ with brief note
- English expression: flag unnatural sentences, suggest better phrasing
- Uses fast/local model to avoid breaking practice flow

### 5. Error Notebook — mistakes → Entry

Wrong pronunciations and expression errors flow into the Entry (vocab) system.

Auto-applied system tags: `pronunciation`, `expression`, `vocabulary`, `phrase`, `interview`.  
`Entry.source_ref` → originating question_id.

Threshold-based auto-add for pronunciation (score < 60). Manual one-click for expression errors.

### 6. Coach Dashboard — replace Daily Plan on Home

Home page shows a coaching brief, not a task list:
- Today's focus (top goal, days remaining)
- Practice plan with reasons ("URL Shortener — last score 2, scaling weak")
- Weekly trend per domain (improving ↑ / stalled → / declining ↓)
- Goals management (add / edit / reorder)

---

## AI Role Allocation

| Role | Trigger | Model |
|------|---------|-------|
| Content creator | On-demand, async | Any |
| Real-time evaluator | After each answer | Local/fast |
| Coach summary | End of session | Local |
| Daily plan generator | Once per day | Local |

No character names. Evaluator tone = direct examiner. Coach tone = explanatory with reasons.

---

## Content Management Principle

Every feature that creates data ships with an inline management UI. No exceptions:
- `key_points` — inline add/edit/delete on question card
- `sub_questions` — inline add/edit/delete, individual self_score
- `QuestionAttempt` — history list per question, deletable
- `CoachGoal` — full CRUD on home page

---

## Implementation Order

| # | Feature | GitHub Issue |
|---|---------|-------------|
| 1 | CoachGoal model + DB + API + Home UI | #51 |
| 2 | key_points + sub_questions on InterviewQuestion | #52 |
| 3 | QuestionAttempt table + history view | #53 |
| 4 | AI Evaluator — coverage + expression | #54 |
| 5 | Error Notebook — pronunciation + expression → Entry | #55 |
| 6 | Coach Dashboard — replace Daily Plan | #56 |

---

## Consequences

- Home page UX changes significantly — existing Daily Plan widget replaced
- `InterviewQuestion` gains two new JSON fields — no migration needed (new columns with null defaults)
- New `question_attempts` table required
- New `coach_goals` table required
- AI usage increases — evaluator runs after every answer; must stay fast

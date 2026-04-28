# NoteMaster

**Your personal learning coach for senior engineering interviews and English fluency.**

NoteMaster is not a note-taking app or a second brain. It is the execution layer that sits on top of your learning tools — it tells you what to practice today, makes you do the reps, and tracks whether you're improving.

---

## What it does

```
Data Sources (plug in what you use)
├── NoteMaster DB       — English vocab, questions, job applications
├── Hello Interview     — SD / LLD curriculum
├── NeetCode roadmap    — Coding problem list
├── Obsidian vault      — Your notes (optional)
└── Web / URL           — Articles → questions
         ↓
    NoteMaster
    (coordinator)
         ↓
    Daily plan  →  Practice  →  Track progress
```

You bring the study materials. NoteMaster decides what to practice today, runs the drill, and keeps score.

---

## Core features

### Daily plan
Auto-generated every morning from your queues. Time-blocked by type:
- **Morning**: System Design + LLD + Coding problem
- **Afternoon**: Behavioral + job search follow-ups
- **Evening**: English vocabulary review + pronunciation drill

You configure the blocks once. The content fills itself from your backlog.

### English practice
- Vocabulary cards with IPA, translation, usage, and example sentences
- Spaced repetition (SM-2) — surfaces words at the right interval
- Pronunciation drill: record yourself, get word-level feedback via Whisper
- Register tagging: spoken (interview English) vs written (reading comprehension)

### Interview preparation
- **Study questions**: generated from articles/guides via AI, organised by topic
- **Behavioral / SD / LLD / Coding**: question bank with spaced repetition
- **Pronunciation practice**: read your answer aloud, get scored
- Links to Hello Interview breakdowns and NeetCode problems — NoteMaster tracks your progress without replacing those tools

### Job search
- Kanban board: Applied → Phone → Technical → Onsite → Offer / Rejected
- Per-application round tracking with round type (HR, Manager, Coding, SD, LLD, Behavioral)
- Per-round: questions asked, preparation notes, practice entry

### Capture (Inbox)
- Paste anything instantly — word, concept, question, link
- AI classifies and routes to the right place
- Pending badge keeps the backlog visible

### AI providers
- Supports local (llama.cpp / Ollama), Groq, OpenAI, Anthropic
- Switch active provider from Admin — all features use the same provider
- Falls back to `.env` config when no provider is activated

---

## What NoteMaster is not

- **Not a knowledge base** — use Obsidian, Notion, or Apple Notes for that
- **Not a flashcard app** — spaced repetition is a means to an end, not the product
- **Not a replacement for Hello Interview or LeetCode** — it coordinates with them

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.11+ · FastAPI |
| Frontend | Single-file responsive PWA |
| Speech-to-text | mlx-whisper (Apple Silicon Neural Engine) |
| AI | Multi-provider: local / Groq / OpenAI / Anthropic |
| Database | SQLite (`data/notemaster.db`) |

All processing runs on your Mac. Mobile connects via browser over local Wi-Fi.

---

## Installation

```bash
git clone <repo>
cd NoteMaster
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Download the Whisper model (~769 MB, one-time):

```bash
python -m scripts.download_model
```

---

## Configuration

```bash
cp .env.example .env
```

Minimal config (local AI):
```bash
AI_BASE_URL=http://192.168.1.81:8080/v1
AI_MODEL=gemma-4-26b
WHISPER_MODEL=medium
```

For cloud AI providers, add providers via **Admin → AI Providers** — no `.env` changes needed.

---

## Running

```bash
source .venv/bin/activate
python -m notemaster serve
```

- Mac: http://localhost:8000
- iPhone / iPad: `http://<mac-local-ip>:8000`

```bash
# Find your Mac's local IP
ipconfig getifaddr en0

# Kill a stuck server
lsof -ti :8000 | xargs kill -9
```

---

## Tests

```bash
source .venv/bin/activate
pytest tests/unit/ -q          # 500+ unit tests, no external deps
pytest tests/unit/test_X.py -v # single file
```

Built TDD-first: every feature starts as a failing test.

---

## Project structure

```
NoteMaster/
├── notemaster/
│   ├── models.py       # Pydantic models
│   ├── db.py           # SQLite CRUD
│   ├── main.py         # FastAPI app + CLI
│   ├── ai.py           # AI: evaluate, enrich, classify, generate
│   ├── providers.py    # AI provider adapter (OpenAI / Anthropic)
│   ├── session.py      # SM-2 spaced repetition
│   ├── stt.py          # Whisper speech-to-text
│   ├── books.py        # Apple Books highlight reader
│   ├── importer.py     # File/PDF import
│   ├── ocr.py          # Image OCR
│   └── config.py       # Env config
├── frontend/
│   └── index.html      # Single-file PWA
├── tests/unit/         # Unit tests
├── docs/features/      # Feature design docs
├── scripts/            # One-off migration and setup scripts
├── data/               # gitignored — database lives here
└── .env.example
```

---

## Roadmap

See [open issues](../../issues) for the full list. Current priorities:

| # | Feature | Why first |
|---|---------|-----------|
| 1 | Daily plan (Home redesign) | Ties everything together into a daily habit |
| 2 | Curriculum: Hello Interview SD/LLD + NeetCode | Gives the daily plan content to draw from |
| 3 | Interview round types + LeetCode entity | Structures job prep properly |
| 4 | Pronunciation practice Level 1 | Highest-friction gap in current workflow |
| 5 | English register / content types | Better spoken vs written drill separation |
| 6 | Source document entity | Audit trail from material → practice |
| 7 | Obsidian datasource integration | One datasource among many, not a dependency |

---

## Privacy

`data/` is gitignored. Nothing leaves your machine unless you configure a cloud AI provider.

# NoteMaster

A local-first study system that turns Apple Books highlights, interview questions, and job applications into a unified knowledge graph — then drives structured spaced-repetition sessions, powered by a self-hosted AI.

## Motivation

Reading technical books is easy. Retaining concepts well enough to explain them in a senior engineering interview is hard. NoteMaster bridges that gap by:

1. Pulling highlights directly from Apple Books and using AI to synthesize them into a connected knowledge graph.
2. Tracking job applications and interview questions alongside your notes so everything lives in one place.
3. Linking interview questions to knowledge concepts — so you know exactly which chapters to revisit when a question trips you up.
4. Driving active recall sessions with AI feedback on both technical depth and English expression.

The backend runs on your Mac. The web UI is accessible from any device on the same local network — Mac, iPhone, or iPad — with no installation required on mobile devices.

## Features

### Knowledge graph
- AI synthesizes highlights into concept nodes and builds a directed graph of relationships (`depends_on`, `contrasts_with`, `part_of`, `example_of`)
- Unified graph view across all books, or filtered per book
- Interview question nodes overlaid on the graph — see at a glance which concepts a question tests

### Spaced repetition
- SM-2 scheduling for both concepts and interview questions
- Concept weight derived from highlight coverage; weight rises when you struggle, falls when you master
- Review priority = `weight × (1 + days overdue)`
- Session modes: concepts, English, mixed, or full interview simulation

### Interview preparation
- Kanban board for tracking job applications (Applied → Phone → Technical → Onsite → Offer / Rejected)
- Interview questions bank with type tags (Behavioral, System Design, Coding) and self-score dots
- Drill down from a Kanban card into questions from a specific interview round
- Link questions to concepts — concept pills appear on question cards; question nodes appear on the graph
- SM-2 review mode for questions: grade Weak / Ok / Strong after each answer

### English learning
- Yellow highlights routed to English vocabulary and sentence pattern review
- AI grades grammar, vocabulary, and naturalness alongside technical depth

### Admin panel
- Inline editing for concepts (title, summary, weight), applications, and questions
- Delete with cascade — removing a concept removes its review history; removing an application removes its rounds

### Import
- Sync highlights from Apple Books via Asset ID
- Import `.txt`, `.md`, or `.pdf` files as concepts
- Migrate from a job-hunt JSON export: `python -m scripts.migrate_job_hunt <file>`

### PWA
- Installable on iPhone / iPad via "Add to Home Screen"
- GitHub-style activity heatmap and daily streak counter

## How it works

```
Apple Books highlights              Job-hunt JSON export
        ↓                                   ↓
   POST /sync                  scripts/migrate_job_hunt.py
        ↓                                   ↓
POST /synthesize               /applications + /questions
        ↓                                   ↓
 GET /session/next ←──── unified priority queue ────→ GET /questions/next
        ↓
POST /answer/text|voice  →  AI evaluation  →  SM-2 reschedule
```

## Knowledge graph

### Concept weight

| Event | Effect on weight |
|-------|-----------------|
| Concept created | `Σ highlight color factors` — GREEN 1.5, BLUE 1.3, YELLOW 1.0 |
| After review | multiplied by mastery factor — score 1 → ×1.4 … score 5 → ×0.7 |
| New highlights added on re-read | recalculated from updated highlight set |

### Edge relation types

| Relation | Meaning |
|----------|---------|
| `depends_on` | understanding A requires understanding B |
| `contrasts_with` | A and B differ in a meaningful way |
| `part_of` | A is a component of B |
| `example_of` | A is a concrete instance of B |
| `tested_by` | concept A is tested by interview question B |

## Highlight color convention

| Color | Meaning | Weight factor |
|-------|---------|--------------|
| Yellow | English vocabulary, phrases, or sentence patterns | 1.0 |
| Green | Technical concepts | 1.5 |
| Blue | Both — an important concept expressed in notable English | 1.3 |

## API reference

### Books & highlights
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/books` | List synced books |
| `POST` | `/sync` | Import highlights from Apple Books |
| `POST` | `/synthesize` | AI synthesis: highlights → concepts + edges |

### Concepts
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/graph` | Knowledge graph (nodes + edges); `?book_id=` filters by book, `?include_questions=true` adds question nodes |
| `GET` | `/graph/books` | List all books for graph selector |
| `GET` | `/concepts/{id}` | Get concept |
| `PATCH` | `/concepts/{id}` | Update title, summary, or weight |
| `DELETE` | `/concepts/{id}` | Delete concept and review history |
| `POST` | `/concepts/{id}/review` | Record review, reschedule |
| `GET` | `/concepts/{id}/questions` | List questions linked to concept |

### Session
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/session/next` | Next item due; `?include_questions=true` mixes in questions |
| `GET` | `/session/queue` | Full priority queue |
| `POST` | `/answer/text` | Submit text answer; get AI evaluation |
| `POST` | `/answer/voice` | Submit voice answer; get AI evaluation |
| `GET` | `/stats` | Streak, heatmap, study sessions |

### Applications
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/applications` | List all applications |
| `POST` | `/applications` | Create application |
| `GET` | `/applications/{id}` | Get application |
| `PATCH` | `/applications/{id}` | Update application |
| `DELETE` | `/applications/{id}` | Delete application + rounds |
| `POST` | `/applications/{id}/rounds` | Add interview round |
| `PATCH` | `/applications/{id}/rounds/{rid}` | Update round |

### Questions
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/questions` | List questions; `?q_type=`, `?due_only=true`, `?application_id=` |
| `POST` | `/questions` | Create question |
| `GET` | `/questions/next` | Next question due for SM-2 review |
| `POST` | `/questions/import` | Bulk import |
| `GET` | `/questions/{id}` | Get question |
| `PATCH` | `/questions/{id}` | Update question |
| `DELETE` | `/questions/{id}` | Delete question |
| `POST` | `/questions/{id}/review` | Record SM-2 review (grade 1–3) |
| `GET` | `/questions/{id}/concepts` | List linked concepts |
| `POST` | `/questions/{id}/concepts` | Link concept to question |
| `DELETE` | `/questions/{id}/concepts/{concept_id}` | Unlink concept |

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | Python + FastAPI |
| Frontend | Responsive PWA — works in browser on Mac, iPhone, and iPad |
| Speech-to-text | mlx-whisper — runs on Apple Silicon Neural Engine |
| AI | Self-hosted via llama.cpp (OpenAI-compatible API) |
| App database | SQLite |
| Highlight source | Apple Books SQLite (read-only, auto-detected) |

All processing happens on your Mac. Mobile devices connect via browser over local Wi-Fi — no app installation needed. Adding the page to the home screen on iOS gives a near-native experience via PWA.

## Requirements

**Mac (server)**
- macOS with Apple Silicon (M1 or later)
- Python 3.11+
- Apple Books with highlights
- A running [llama.cpp](https://github.com/ggerganov/llama.cpp) server exposing an OpenAI-compatible API

**iPhone / iPad (client)**
- iOS 14.3+ or iPadOS 14.3+
- Safari or any modern browser
- Connected to the same local Wi-Fi as the Mac

## Installation

```bash
git clone https://github.com/your-username/NoteMaster.git
cd NoteMaster
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On first run, NoteMaster downloads the Whisper medium model (~769 MB):

```bash
python -m scripts.download_model
```

## Configuration

Copy the example env file and fill in your local AI server details:

```bash
cp .env.example .env
```

```bash
# .env
AI_BASE_URL=http://<your-local-ai-server>/v1
AI_MODEL=<model-name>
WHISPER_MODEL=medium
```

The Apple Books annotation database is located automatically — no path configuration needed.

## Usage

**Start the server**

```bash
.venv/bin/python -m notemaster serve
```

- Mac: [http://localhost:8000](http://localhost:8000)
- iPhone / iPad: `http://<mac-local-ip>:8000` (same Wi-Fi)

**Sync highlights from Apple Books**

Find the asset ID for a book:

```bash
sqlite3 ~/Library/Containers/com.apple.iBooksX/Data/Documents/BKLibrary/BKLibrary-1-091020131601.sqlite \
  "SELECT ZASSETID, ZTITLE FROM ZBKLIBRARYASSET WHERE ZTITLE LIKE '%<book name>%';"
```

Then sync via the app's **Sync** button or the API:

```bash
.venv/bin/python -m notemaster sync <asset_id> "<book title>"
```

**Migrate from job-hunt**

Export your data from job-hunt (localStorage → JSON), then:

```bash
.venv/bin/python -m scripts.migrate_job_hunt path/to/export.json
# dry run first:
.venv/bin/python -m scripts.migrate_job_hunt path/to/export.json --dry-run
```

## Privacy

- `data/` is gitignored — your progress database never leaves your machine
- Highlights are read directly from Apple Books and only sent to your local AI server
- No usernames, IP addresses, or machine paths appear in the source code

## Project structure

```
NoteMaster/
├── notemaster/
│   ├── models.py       # Pydantic models: Book, Concept, Application, InterviewQuestion, …
│   ├── books.py        # Read highlights from Apple Books SQLite
│   ├── stt.py          # mlx-whisper transcription
│   ├── ai.py           # evaluate() + synthesize() agentic loop
│   ├── tools.py        # AI tool schemas + ToolHandler
│   ├── session.py      # Session scheduling and spaced repetition
│   ├── db.py           # SQLite: concepts, edges, reviews, applications, questions
│   └── main.py         # FastAPI app and CLI entry point
├── frontend/
│   └── index.html      # Single-file PWA
├── tests/
│   ├── unit/           # 355+ unit tests, no external deps
│   └── integration/
├── scripts/
│   ├── download_model.py
│   └── migrate_job_hunt.py
├── data/               # gitignored
├── .env.example
├── requirements.txt
└── README.md
```

## Development

### TDD methodology

This project is built test-first. Every new behaviour is written as a failing test before any implementation.

**Test split:**

| Group | Command | When to run |
|-------|---------|-------------|
| Unit | `pytest tests/unit/` | Always — no external dependencies |
| Integration | `pytest -m integration` | Manually — requires local AI server and Apple Books |

**Unit test coverage by module:**

| File | What it covers |
|------|---------------|
| `test_models.py` | Pydantic validation |
| `test_books.py` | Apple Books SQLite reader |
| `test_db.py` | Concepts, edges, weight helpers, review scheduling |
| `test_tools.py` | AI tool schemas and ToolHandler dispatch |
| `test_ai.py` | AI evaluation and prompt content |
| `test_session.py` | Session filtering and card selection |
| `test_main.py` | FastAPI endpoints |
| `test_job_hunt_db.py` | Applications and questions CRUD + SM-2 |
| `test_applications_api.py` | Applications API |
| `test_questions_api.py` | Questions API |
| `test_unified_queue.py` | Mixed review queue across note types |
| `test_question_concept_links.py` | Question ↔ Concept link DB and API |
| `test_unified_graph.py` | Graph endpoint with question nodes |
| `test_migrate_job_hunt.py` | Migration script |

**Running tests:**

```bash
# All unit tests (fast, no external deps)
.venv/bin/pytest tests/unit/

# Single file
.venv/bin/pytest tests/unit/test_questions_api.py -v
```

**TDD workflow for new features:**
1. Write a failing test in the appropriate `tests/unit/` file
2. Implement the minimum code to make it pass
3. Refactor — tests stay green throughout

## License
TODO

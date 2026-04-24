# NoteMaster

A local-first study system that captures anything, turns Apple Books highlights and interview material into a connected knowledge graph, and drives structured spaced-repetition sessions — powered by a self-hosted AI.

## Motivation

Reading technical books is easy. Retaining concepts well enough to explain them in a senior engineering interview is hard. NoteMaster bridges that gap by:

1. Pulling highlights directly from Apple Books and using AI to synthesize them into a connected knowledge graph.
2. Capturing fleeting notes instantly and routing them to the right place — English vocab, concept, or interview question.
3. Tracking job applications and interview questions alongside your notes so everything lives in one place.
4. Linking interview questions to knowledge concepts — so you know exactly which chapters to revisit when a question trips you up.
5. Driving active recall sessions with AI feedback on both technical depth and English expression.

The backend runs on your Mac. The web UI is accessible from any device on the same local network — Mac, iPhone, or iPad — with no installation required on mobile.

---

## Features

### Capture (quick-capture inbox)
- Paste or type anything quickly — a word, a concept, a question — without deciding where it goes
- Pending count badge on the home screen so nothing gets forgotten
- Per-item routing buttons: send directly to English, Concept, or Question
- **AI Classify**: one click to get a type suggestion + structured preview, then confirm with a single tap

### English vocabulary
- Vocabulary and phrase cards with IPA phonetics, Chinese translation, usage note, and example sentences
- Extended attributes (tenses, word forms, root, synonyms, derivatives) generated selectively via AI
- All fields inline-editable; batch AI enrichment for multiple entries at once
- Spaced-repetition review with pronunciation check (speech-to-text via Whisper)

### Knowledge graph
- AI synthesizes highlights into concept nodes with a directed relationship graph (`depends_on`, `contrasts_with`, `part_of`, `example_of`)
- Unified graph view across all books, or filtered per book
- Interview question nodes overlaid on the graph — see at a glance which concepts a question tests

### Spaced repetition
- SM-2 scheduling for concepts, English entries, and interview questions
- Concept weight derived from highlight coverage; rises when you struggle, falls when you master
- Review priority = `weight × (1 + days overdue)`
- Session modes: concepts, English, mixed, or full interview simulation

### Interview preparation
- Kanban board for tracking job applications (Applied → Phone → Technical → Onsite → Offer / Rejected)
- Interview questions bank with type tags (Behavioral, System Design, Coding) and self-score dots
- Drill down from a Kanban card into questions from a specific interview round
- Link questions to concepts — concept pills appear on question cards; question nodes appear on the graph

### Import
- Sync highlights from Apple Books via Asset ID
- Import `.txt`, `.md`, or `.pdf` files as concepts
- Import from transcript text (auto-extract questions)
- Migrate from a job-hunt JSON export: `python -m scripts.migrate_job_hunt <file>`

### Admin panel
- Full modal editing for English entries — all 9 fields in one view
- Inline editing for concepts (title, summary, weight), applications, and questions
- Delete with cascade

### PWA
- Installable on iPhone / iPad via "Add to Home Screen"
- GitHub-style activity heatmap and daily streak counter

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.11+ + FastAPI |
| Frontend | Single-file responsive PWA — works in browser on Mac, iPhone, and iPad |
| Speech-to-text | mlx-whisper — runs on Apple Silicon Neural Engine |
| AI | Self-hosted via llama.cpp / Ollama (OpenAI-compatible API) |
| Database | SQLite (`data/notemaster.db`) |
| Highlight source | Apple Books SQLite (read-only, auto-detected) |

All processing happens on your Mac. Mobile devices connect via browser over local Wi-Fi.

---

## Requirements

**Mac (server)**
- macOS with Apple Silicon (M1 or later)
- Python 3.11+
- A running llama.cpp or Ollama server exposing an OpenAI-compatible API at a local address

**iPhone / iPad (client)**
- iOS 14.3+ / iPadOS 14.3+
- Safari or any modern browser, same Wi-Fi as the Mac

---

## Installation

```bash
git clone <repo>
cd NoteMaster
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Download the Whisper speech model (~769 MB, one-time):

```bash
python -m scripts.download_model
```

---

## Configuration

```bash
cp .env.example .env
```

Edit `.env`:

```bash
AI_BASE_URL=http://192.168.1.81:8080/v1   # your local AI server
AI_MODEL=gemma-4-26b                       # model name as reported by the server
WHISPER_MODEL=medium
```

---

## Starting the server

```bash
source .venv/bin/activate
python -m notemaster serve
```

- Mac: http://localhost:8000
- iPhone / iPad: `http://<mac-local-ip>:8000`

To find your Mac's local IP:

```bash
ipconfig getifaddr en0
```

The server runs with `--reload` by default in development, so file changes take effect immediately.

---

## Restarting

Stop the server with `Ctrl-C`, then start it again:

```bash
python -m notemaster serve
```

If the port is already in use (e.g. after a crash):

```bash
lsof -ti :8000 | xargs kill -9
python -m notemaster serve
```

---

## Troubleshooting

### Server won't start

**Port already in use**
```
ERROR: [Errno 48] Address already in use
```
```bash
lsof -ti :8000 | xargs kill -9
```

**Module not found**
```
ModuleNotFoundError: No module named 'notemaster'
```
Virtualenv is not activated:
```bash
source .venv/bin/activate
```

**Missing dependencies**
```bash
pip install -r requirements.txt
```

---

### AI features not working

**Symptoms**: AI Classify spins forever, enrichment never fills in, no feedback after answering.

1. Check the local AI server is reachable:
   ```bash
   curl http://192.168.1.81:8080/v1/models
   ```
   Should return a JSON list of models.

2. Check `.env` — `AI_BASE_URL` must have no trailing slash; `AI_MODEL` must match exactly what the server reports.

3. Check the server terminal for tracebacks. AI calls in background tasks fail silently but print to stdout.

4. Quick connectivity test:
   ```bash
   source .venv/bin/activate
   python - <<'EOF'
   from openai import OpenAI
   from notemaster.config import AI_BASE_URL, AI_MODEL
   c = OpenAI(base_url=AI_BASE_URL, api_key="not-used")
   r = c.chat.completions.create(model=AI_MODEL, messages=[{"role":"user","content":"ping"}])
   print(r.choices[0].message.content)
   EOF
   ```

**Slow responses**: Long inputs (synthesizing a full book) take minutes on a local model — this is expected.

---

### Speech input not working

**Symptoms**: Mic button does nothing, or voice answers are not transcribed.

1. Confirm the Whisper model was downloaded:
   ```bash
   ls ~/.cache/huggingface/hub/ | grep whisper
   ```
   If empty: `python -m scripts.download_model`

2. Check browser microphone permission — Safari on iOS requires explicit permission per site.

3. The browser must connect via `http://localhost` or HTTPS. Accessing via LAN IP (`http://192.168.x.x:8000`) blocks the microphone in iOS Safari. Workaround: use a local HTTPS proxy (e.g. `caddy reverse-proxy --from https://notemaster.local --to http://localhost:8000`) or connect via USB/Bonjour.

---

### Apple Books sync not working

**Symptoms**: Sync returns an error or finds no highlights.

1. Confirm Apple Books has been opened and the book has highlights.

2. Check the Books database exists:
   ```bash
   ls ~/Library/Containers/com.apple.iBooksX/Data/Documents/BKLibrary/
   ```

3. Find the Asset ID for your book:
   ```bash
   sqlite3 ~/Library/Containers/com.apple.iBooksX/Data/Documents/BKLibrary/BKLibrary-1-091020131601.sqlite \
     "SELECT ZASSETID, ZTITLE FROM ZBKLIBRARYASSET WHERE ZTITLE LIKE '%<book name>%';"
   ```

4. macOS may prompt for Full Disk Access — grant it to the terminal app you use.

---

### Database issues

The database lives at `data/notemaster.db` and is created automatically on first run. It is gitignored.

**Reset the database** (destructive — loses all data):
```bash
rm data/notemaster.db
python -m notemaster serve   # recreates schema on startup
```

**Inspect directly**:
```bash
sqlite3 data/notemaster.db
.tables
SELECT * FROM inbox_items WHERE processed_at IS NULL;
SELECT count(*) FROM entries;
```

---

## Running tests

```bash
source .venv/bin/activate

# All unit tests (fast, no external deps)
pytest tests/unit/ -q

# Single file
pytest tests/unit/test_inbox_api.py -v

# Integration tests (requires local AI server + Apple Books)
pytest -m integration
```

The test suite has 471 unit tests, all running against an in-memory SQLite database with mocked AI clients.

---

## Project structure

```
NoteMaster/
├── notemaster/
│   ├── models.py       # Pydantic models for all entities
│   ├── db.py           # SQLite CRUD for all tables
│   ├── main.py         # FastAPI app + CLI entry point
│   ├── ai.py           # AI: evaluate, synthesize, enrich, classify
│   ├── books.py        # Apple Books highlight reader
│   ├── session.py      # Spaced repetition scheduling
│   ├── stt.py          # Whisper speech-to-text
│   ├── tools.py        # AI tool schemas + ToolHandler
│   ├── importer.py     # File/PDF import
│   ├── ocr.py          # Image OCR import
│   └── config.py       # Env-based configuration
├── frontend/
│   ├── index.html      # Single-file PWA
│   ├── favicon.svg
│   └── icon-192.png
├── tests/
│   ├── unit/           # 471 unit tests, no external deps
│   └── integration/
├── scripts/
│   ├── download_model.py
│   ├── migrate_job_hunt.py
│   └── migrate_entries_data.py
├── data/               # gitignored — your database lives here
├── .env.example
├── requirements.txt
└── README.md
```

---

## API quick reference

### Capture
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/inbox` | Create capture item |
| `GET` | `/inbox` | List items; `?pending_only=true` |
| `GET` | `/inbox/pending-count` | Pending count |
| `PATCH` | `/inbox/{id}` | Update content or tags |
| `DELETE` | `/inbox/{id}` | Dismiss item |
| `POST` | `/inbox/{id}/classify` | AI classify → type + preview |
| `POST` | `/inbox/{id}/route` | Route to English / Concept / Question |

### English entries
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/entries` | List entries |
| `POST` | `/entries` | Create (triggers background AI enrich) |
| `PATCH` | `/entries/{id}` | Update text or data fields |
| `DELETE` | `/entries/{id}` | Delete |
| `POST` | `/entries/{id}/enrich` | Re-run AI enrichment |
| `POST` | `/entries/{id}/enrich/extra` | AI enrich specific extra fields |
| `POST` | `/entries/batch-enrich` | Batch enrich selected entries |
| `GET` | `/entries/next` | Next entry due for review |
| `POST` | `/entries/{id}/review` | Record SM-2 review |

### Books & highlights
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/books` | List synced books |
| `POST` | `/sync` | Import highlights from Apple Books |
| `POST` | `/synthesize` | AI synthesis: highlights → concepts + edges |

### Concepts
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/graph` | Knowledge graph; `?book_id=`, `?include_questions=true` |
| `GET` | `/concepts/{id}` | Get concept |
| `PATCH` | `/concepts/{id}` | Update |
| `DELETE` | `/concepts/{id}` | Delete with cascade |
| `POST` | `/concepts/{id}/review` | Record review |

### Session
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/session/next` | Next item due |
| `POST` | `/answer/text` | Submit text answer + AI evaluation |
| `POST` | `/answer/voice` | Submit voice answer + AI evaluation |
| `GET` | `/stats` | Streak, heatmap, session history |

### Applications
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/applications` | List |
| `POST` | `/applications` | Create |
| `PATCH` | `/applications/{id}` | Update |
| `DELETE` | `/applications/{id}` | Delete + rounds |
| `POST` | `/applications/{id}/rounds` | Add interview round |
| `PATCH` | `/applications/{id}/rounds/{rid}` | Update round |

### Questions
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/questions` | List; `?q_type=`, `?due_only=true`, `?application_id=` |
| `POST` | `/questions` | Create |
| `GET` | `/questions/next` | Next due for SM-2 review |
| `POST` | `/questions/import` | Bulk import |
| `PATCH` | `/questions/{id}` | Update |
| `DELETE` | `/questions/{id}` | Delete |
| `POST` | `/questions/{id}/review` | Record SM-2 review |
| `GET` | `/questions/{id}/concepts` | Linked concepts |
| `POST` | `/questions/{id}/concepts` | Link concept |
| `DELETE` | `/questions/{id}/concepts/{cid}` | Unlink concept |

---

## Privacy

- `data/` is gitignored — your database never leaves your machine
- Highlights are read directly from Apple Books and sent only to your local AI server
- No external network calls

---

## Development

This project is built test-first. Every new behaviour is written as a failing test before implementation.

```bash
# Run all unit tests
pytest tests/unit/ -q

# TDD workflow:
# 1. Write a failing test
# 2. Implement minimum code to pass
# 3. Refactor — tests stay green
```

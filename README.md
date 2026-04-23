# NoteMaster

A local-first study system that turns Apple Books highlights into a knowledge graph, then drives structured interview preparation and English learning sessions — powered by a self-hosted AI.

## Motivation

Reading technical books is easy. Retaining concepts well enough to explain them in a senior engineering interview is hard. NoteMaster bridges that gap by pulling highlights directly from Apple Books, using AI to synthesize them into a connected knowledge graph, and then driving active recall sessions — with AI feedback on both technical depth and English expression.

The backend runs on your Mac. The web UI is accessible from any device on the same local network — Mac, iPhone, or iPad — with no installation required on mobile devices.

## Features

- **Knowledge graph** — AI synthesizes highlights into concept nodes and builds a directed graph of relationships (depends on, contrasts with, part of, example of)
- **Weight-based review queue** — each concept carries a weight derived from its highlight coverage; weight rises when you struggle, falls when you master the concept, and drives how often it appears in review
- **Session modes** — choose duration (5 / 10 / 20 min or custom) and focus area: concepts, English, mixed, or full interview simulation
- **Voice or text input** — answer out loud or type; voice is transcribed locally on-device
- **Dual AI feedback** — one evaluation grades technical accuracy and Senior Backend depth; another grades English grammar, vocabulary, and naturalness
- **Spaced repetition** — SM-2 scheduling, modulated by concept weight so high-weight concepts resurface more frequently
- **Streak and heatmap** — GitHub-style activity heatmap and daily streak counter to track consistency

## How it works

```
Apple Books highlights
        ↓
   POST /sync          — import highlights for a book
        ↓
POST /synthesize       — AI agentic loop: group highlights into concepts, build graph edges
        ↓
 GET /session/next     — pick next concept by weight × urgency
        ↓
POST /answer/text|voice — evaluate answer, update weight, schedule next review
```

## Knowledge graph

Highlights are the raw signal; concepts are the knowledge units the review system operates on.

### Concept weight

| Event | Effect on weight |
|-------|-----------------|
| Concept created | `Σ highlight color factors` — GREEN 1.5, BLUE 1.3, YELLOW 1.0 |
| After review | multiplied by mastery factor — score 1 → ×1.4 … score 5 → ×0.7 |
| New highlights added on re-read | recalculated from updated highlight set |

Higher weight → shorter SM-2 intervals → reviewed more often.
Review priority = `weight × (1 + days overdue)`.

### Edge relation types

| Relation | Meaning |
|----------|---------|
| `depends_on` | understanding A requires understanding B |
| `contrasts_with` | A and B differ in a meaningful way |
| `part_of` | A is a component of B |
| `example_of` | A is a concrete instance of B |

## Highlight color convention

NoteMaster reads highlight color from Apple Books to route each item to the right learning track and set initial concept weight:

| Color | Meaning | Weight factor |
|-------|---------|--------------|
| Yellow | English vocabulary, phrases, or sentence patterns | 1.0 |
| Green | Technical concepts | 1.5 |
| Blue | Both — an important concept expressed in notable English | 1.3 |

## API reference

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/books` | List synced books |
| `POST` | `/sync` | Import highlights from Apple Books |
| `POST` | `/synthesize` | AI synthesis: highlights → concepts + edges |
| `GET` | `/session/next` | Next concept due for review |
| `GET` | `/session/queue` | Full priority queue |
| `POST` | `/answer/text` | Submit text answer; get AI evaluation |
| `POST` | `/answer/voice` | Submit voice answer; get AI evaluation |
| `GET` | `/graph` | Knowledge graph (nodes + edges) |
| `GET` | `/stats` | Streak, heatmap, study sessions |

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

**Stop the server**

```bash
pkill -f "notemaster serve"
```

Or press `Ctrl+C` if running in the foreground.

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

**Build the knowledge graph**

After syncing, trigger AI synthesis to convert highlights into concepts and edges:

```bash
curl -X POST http://localhost:8000/synthesize \
  -H "Content-Type: application/json" \
  -d '{"book_id": "<book_id returned by sync>"}'
```

The AI will group related highlights into concept nodes and link them with typed edges. This runs as an agentic loop — the model calls tools to read highlights, create concepts, and build edges until all highlights are processed.

## Privacy

- `data/` is gitignored — your progress database never leaves your machine
- Highlights are read directly from Apple Books and only sent to your local AI server
- No usernames, IP addresses, or machine paths appear in the source code

## Project structure

```
NoteMaster/
├── notemaster/
│   ├── models.py       # Data models: Book, Highlight, Concept, ConceptEdge, ReviewRecord
│   ├── books.py        # Read highlights from Apple Books SQLite
│   ├── stt.py          # mlx-whisper transcription
│   ├── ai.py           # evaluate() + synthesize() agentic loop
│   ├── tools.py        # AI tool schemas (SYNTHESIS_TOOLS, REVIEW_TOOLS) + ToolHandler
│   ├── session.py      # Session scheduling and spaced repetition
│   ├── db.py           # App database: books, concepts, edges, reviews, stats
│   └── main.py         # FastAPI app and CLI entry point
├── frontend/
│   └── index.html
├── tests/
│   ├── fixtures/       # Test SQLite and sample audio
│   ├── unit/
│   └── integration/
├── scripts/
│   └── download_model.py
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
| `test_models.py` | Pydantic validation — field types, ranges, required fields |
| `test_books.py` | Apple Books SQLite reader — color mapping, filtering, deleted highlights |
| `test_db.py` | Database layer — Books, Highlights, Concepts, Edges, weight helpers, review scheduling, study sessions |
| `test_tools.py` | AI tool schemas — required params, ToolHandler dispatch, weight side-effects per tool call |
| `test_ai.py` | AI evaluation — prompt content, JSON parsing, markdown code block handling |
| `test_session.py` | Highlight-level session filtering — focus area routing, card selection modes |
| `test_main.py` | FastAPI endpoints — status codes, request validation, mock DB/AI wiring |

**Running tests:**

```bash
# All unit tests (fast, no external deps)
pytest tests/unit/

# Single file
pytest tests/unit/test_tools.py -v

# Integration tests (requires AI server + Apple Books)
pytest -m integration
```

**TDD workflow for new features:**
1. Write a failing test in the appropriate `tests/unit/` file
2. Implement the minimum code to make it pass
3. Refactor — tests stay green throughout

## License
TODO

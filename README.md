# NoteMaster

A local-first study system that turns Apple Books highlights into structured interview preparation and English learning sessions, powered by a self-hosted AI.

## Motivation

Reading technical books is easy. Retaining concepts well enough to explain them in a senior engineering interview is hard. NoteMaster bridges that gap by pulling highlights directly from Apple Books and turning them into active recall sessions — with AI feedback on both technical depth and English expression.

The backend runs on your Mac. The web UI is accessible from any device on the same local network — Mac, iPhone, or iPad — with no installation required on mobile devices.

## Features

- **Session modes** — choose duration (5 / 10 / 20 min or custom) and focus area: concepts, English, mixed, or full interview simulation
- **Voice or text input** — answer out loud or type; voice is transcribed locally on-device
- **Dual AI feedback** — one evaluation grades technical accuracy and Senior Backend depth; another grades English grammar, vocabulary, and naturalness
- **Timed quiz** — each session ends with a 60-second-per-question quiz across three question types: define, error-correction, and scenario
- **Spaced repetition** — items are scheduled by mastery score so weak spots resurface more often
- **Streak and heatmap** — GitHub-style activity heatmap and daily streak counter to track consistency

## Highlight color convention

NoteMaster reads highlight color from Apple Books to route each item to the right learning track:

| Color | Meaning | Learning track |
|-------|---------|----------------|
| Yellow | English vocabulary, phrases, or sentence patterns | English track |
| Green | Technical concepts | Concept track |
| Blue | Both — an important concept expressed in notable English | Both tracks |

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

Open the app in the browser, click **Sync** in the top-right corner, enter the book's asset ID and title. To find the asset ID for a book:

```bash
sqlite3 ~/Library/Containers/com.apple.iBooksX/Data/Documents/BKLibrary/BKLibrary-1-091020131601.sqlite \
  "SELECT ZASSETID, ZTITLE FROM ZBKLIBRARYASSET WHERE ZTITLE LIKE '%<book name>%';"
```

## Privacy

- `data/` is gitignored — your progress database never leaves your machine
- Highlights are read directly from Apple Books and only sent to your local AI server
- No usernames, IP addresses, or machine paths appear in the source code

## Project structure

```
NoteMaster/
├── notemaster/
│   ├── models.py       # Data models: Highlight, EvaluationResult, SessionConfig
│   ├── books.py        # Read highlights from Apple Books SQLite
│   ├── stt.py          # mlx-whisper transcription
│   ├── ai.py           # Prompts and local AI API calls
│   ├── session.py      # Session scheduling and spaced repetition
│   ├── db.py           # App database: progress, streak, quiz results
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

This project follows TDD. Tests are split into two groups:

```bash
pytest -m unit          # No external dependencies, runs anywhere
pytest -m integration   # Requires local AI server and Apple Books; run manually
```

## License
TODO
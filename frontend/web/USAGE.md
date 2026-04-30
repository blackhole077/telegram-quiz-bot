# Quiz Web UI

A FastAPI + HTMX web interface for the quiz system.

## Setup

1. Activate the project virtualenv from the repo root:

   ```bash
   source .venv/bin/activate
   ```

2. Create a `.env` file at the repo root if you haven't already:

   ```plain
   DATA_DIR=/path/to/your/data
   STORAGE_TYPE=filesystem
   ```

   Defaults: `data_dir=/data`, `storage_type=filesystem`. See `core/config.py` for all options.

3. Make sure the data directory exists and contains `questions.json`.

## Running

Start the server from the repo root:

```bash
uvicorn web.main:app --reload
```

Then open `http://localhost:8000` in your browser.

The `--reload` flag watches for code changes and restarts automatically.

## How It Works

The index page shows your total question count and how many are due today. Click **Start Quiz** to begin a session. Each question is loaded as an HTML fragment via HTMX - the page never fully reloads.

- Click an answer option to submit it immediately
- Feedback (correct/incorrect, explanation, source reference) appears in place
- Click **Next Question** to advance, or **See Results** after the final question
- The summary shows your score and a button to start a new session

SRS scheduling runs automatically: correct answers advance a question's review interval; wrong answers demote it.

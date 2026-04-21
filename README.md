# telegram-quiz-bot

A personal Telegram bot that delivers spaced-repetition quiz sessions. Questions are selected based on a simple SRS schedule, served one at a time, and the bot updates each question's level after every answer.

Single-user by design — one `ALLOWED_USER_ID` is enforced at the bot level.

## Features

- Multiple-choice and free-text question types
- Spaced-repetition scheduling (levels advance on correct answers, demote on wrong)
- `/quiz` — start a session of due questions
- `/stats` — pool size, due count, and current streak
- `/cancel` — end a session early (progress saved)
- Two storage backends: filesystem (JSON + JSONL) or SQLite

## Project layout

```
bot/        Telegram bot and Docker config
quiz/       Core logic: SRS, question formatting, storage, schemas
sync/       Shell scripts to push/pull data files
tests/      pytest suite
data/       Question pool and answer log (not committed — private)
```

## Configuration

Copy `bot/.env.example` to `bot/.env` and fill in the values:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_USER_ID=your_telegram_user_id_here
DATA_DIR=/data
```

Optional settings (with defaults):

| Variable | Default | Description |
|---|---|---|
| `STORAGE_TYPE` | `filesystem` | `filesystem` or `sqlite` |
| `DB_PATH` | `/data/quiz.db` | Path for the SQLite database |

## Running with Docker

```bash
cd bot
docker compose up -d
```

The container mounts `../data` at `/data` for persistent question and answer storage.

## Running locally

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync
source .venv/bin/activate
python -m bot.bot
```

Place `.env` at the repo root when running this way.

## Development

```bash
uv sync
source .venv/bin/activate

# Tests (excludes test_data.py which requires a local data/questions.json)
pytest tests/ --ignore=tests/test_data.py

# Type checking
mypy bot/bot.py
```

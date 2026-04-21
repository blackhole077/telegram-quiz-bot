FROM python:3.12-slim
ARG CACHEBUST=1
WORKDIR /app

# Copy only what the bot needs — no ML deps
COPY pyproject.toml .
COPY quiz/ ./quiz/
COPY bot/bot.py bot/config.py bot/__init__.py ./bot/

RUN pip install --no-cache-dir \
    "python-telegram-bot==21.*" \
    "pydantic>=2.0" \
    "pydantic-settings>=2.0"

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "bot.bot"]

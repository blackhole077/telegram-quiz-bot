# Stage 1: fetch tectonic binary
FROM python:3.12-slim AS tectonic-fetch
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL \
    https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz \
    | tar -xz -C /usr/local/bin/

# Stage 2: runtime image
FROM python:3.12-slim
WORKDIR /app

COPY --from=tectonic-fetch /usr/local/bin/tectonic /usr/local/bin/tectonic

COPY pyproject.toml .
COPY core/ ./core/
COPY backend/ ./backend/
COPY bot/ ./bot/

RUN pip install --no-cache-dir .

# Pre-warm tectonic package cache so /exam doesn't need network at runtime
RUN python -c "
import subprocess, pathlib
tex = r'''
\documentclass{article}
\usepackage[utf8]{inputenc}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{mathtools}
\usepackage{enumitem}
\usepackage{etoolbox}
\usepackage{graphicx}
\usepackage{parskip}
\begin{document}
\(E = mc^2\)
\end{document}
'''
p = pathlib.Path('/tmp/warmup.tex')
p.write_text(tex)
subprocess.run(['tectonic', str(p)], check=True, cwd='/tmp')
p.unlink()
pathlib.Path('/tmp/warmup.pdf').unlink(missing_ok=True)
"

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "bot.bot"]

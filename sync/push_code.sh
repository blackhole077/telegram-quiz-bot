#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_SSH_HOST}"
REMOTE_APP_PATH="${REMOTE_APP_PATH}"   # e.g. /volume1/quiz-bot

REPO_ROOT="$(dirname "$0")/.."

rsync -avz --checksum --delete \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='data/' \
    --exclude='bot/.env' \
    --exclude='.mypy_cache/' \
    --exclude='.pytest_cache/' \
    -e "ssh -p 9022"\
    "$REPO_ROOT/" \
    "${REMOTE_HOST}:${REMOTE_APP_PATH}/"

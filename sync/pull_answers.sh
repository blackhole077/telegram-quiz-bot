#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_SSH_HOST}"
REMOTE_DATA_PATH="${REMOTE_DATA_PATH}"
LOCAL_LOG="${1:-$(dirname "$0")/../data/answers.jsonl}"

mkdir -p "$(dirname "$LOCAL_LOG")"

rsync -avz --checksum --ignore-missing-args -e ssh \
    "${REMOTE_HOST}:${REMOTE_DATA_PATH}/answers.jsonl" \
    "$LOCAL_LOG" || {
    echo "Note: no answer log on remote host yet"
    exit 0
}

echo "Answer log pulled to $LOCAL_LOG"

LOCAL_POOL="$(dirname "$LOCAL_LOG")/questions.json"
rsync -avz --checksum --ignore-missing-args -e ssh \
    "${REMOTE_HOST}:${REMOTE_DATA_PATH}/questions.json" \
    "$LOCAL_POOL" || true

echo "Pool pulled to $LOCAL_POOL"

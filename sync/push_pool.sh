#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_SSH_HOST}"
REMOTE_DATA_PATH="${REMOTE_DATA_PATH}"
LOCAL_POOL="${1:-$(dirname "$0")/../data/questions.json}"

if [[ ! -f "$LOCAL_POOL" ]]; then
    echo "Error: question pool not found at $LOCAL_POOL" >&2
    exit 1
fi

rsync -avz --checksum -e "ssh -p 9022" \
    "$LOCAL_POOL" \
    "${REMOTE_HOST}:${REMOTE_DATA_PATH}/questions.json"

echo "Pool pushed: $(wc -c < "$LOCAL_POOL") bytes"

#!/bin/sh
# Start the FHIR4DS server, publish to the private HF dataset, seed definitions.
#
# The server is the container's main process; seeding runs in a background
# subshell that only polls /health and POSTs the demo artifacts, so a seeding
# failure can never take the surface down.
#
# HF_TOKEN arrives as a Space secret (environment); the publish backend reads
# it through huggingface_hub.
set -eu

PORT="${PORT:-7860}"
APP_DIR=/home/user/app
DATASET="${DATASET:-fhir4ds/bulk-publish-demo-data}"

# Persistent storage, when enabled, mounts /data owned by UID 1000: keep the
# publish cache (dataset snapshot) there so restarts reuse it. Without it,
# /tmp works — meta/state.json lives in the Hub repo, so _seq still survives.
if [ -d /data ] && [ -w /data ]; then
    PUBLISH_DIR=/data/publish
    mkdir -p "$PUBLISH_DIR"
else
    PUBLISH_DIR=/tmp/fhir4ds-publish
fi

python -m fhir4ds.serve \
    --host 0.0.0.0 \
    --port "$PORT" \
    --data-root "$APP_DIR/data" \
    --resources "$APP_DIR/data/smart" \
    --publish-backend hf \
    --publish-repository "$DATASET" \
    --publish-dir "$PUBLISH_DIR" \
    --log-config "$APP_DIR/uvicorn-log.json" &
server_pid=$!

(
    attempt=0
    while [ "$attempt" -lt 240 ]; do
        if curl -fsS "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1; then
            break
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    python "$APP_DIR/seed_registries.py" "http://127.0.0.1:${PORT}" \
        || echo "seed: demo registries not seeded (surface stays up)"
) &

wait "$server_pid"

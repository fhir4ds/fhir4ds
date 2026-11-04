# syntax=docker/dockerfile:1
#
# fhir4ds serve — Hugging Face Docker Space (bulk-publish demo server).
#
# Differs from the production image (deploy/docker/fhir4ds-serve/Dockerfile):
#   1. installs the wheel baked next to this Dockerfile (built from the dev
#      tree — carries boot-time dataset rehydration, which the PyPI 0.0.20
#      pin predates; revert to the PyPI install when a release ships it);
#   2. runs as UID 1000 — Hugging Face starts the container as user 1000;
#   3. ships the demo seed: SMART scheduling-links NDJSON (Slot/Schedule/
#      Location/PractitionerRole/Device) plus the definition registries.
#
# duckdb is pinned to the ABI the bundled C++ extensions were built against.
# A newer duckdb silently refuses the extension and falls back to Python UDFs,
# which is a behavioural change, not a warning.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HOME=/home/user

# curl exists only for HEALTHCHECK: the slim base ships no reliable HTTP client.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ARG DUCKDB_VERSION=1.5.5
RUN python -m pip install --no-cache-dir \
        "fhir4ds-v2[serve,hf]==0.0.21" \
        "duckdb==${DUCKDB_VERSION}"
# Hugging Face runs the container as UID 1000; create it before any COPY so
# the application files are owned by the runtime user.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin user

WORKDIR /home/user/app
COPY --chown=user:user uvicorn-log.json start.sh seed_registries.py ./
COPY --chown=user:user data ./data

USER user

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:7860/health || exit 1

# exec-form-free wrapper: the server runs as a child so the seeding task can
# poll /health without blocking the container's main process or SIGTERM.
CMD ["sh", "/home/user/app/start.sh"]

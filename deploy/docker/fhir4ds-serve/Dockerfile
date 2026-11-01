# syntax=docker/dockerfile:1
#
# fhir4ds serve — one container, two FHIR surfaces:
#   * the SQL-on-FHIR v2 operations (`$sqlquery-run`, ViewDefinition `$run`)
#   * the `$cql` conformance facade at /fhir/$cql (cqframework/cql-tests-runner)
#
# Build context is the REPOSITORY ROOT:
#   docker build -f deploy/docker/fhir4ds-serve/Dockerfile .
#
# No data and no secrets live in the image: data is a mount (see README), and
# HF_TOKEN is supplied at run time with -e/--env-file.

FROM python:3.11-slim

LABEL org.opencontainers.image.title="fhir4ds serve" \
      org.opencontainers.image.description="FHIR R4 HTTP surface for SQL-on-FHIR: \$sqlquery-run, ViewDefinition \$run, and the \$cql conformance facade" \
      org.opencontainers.image.source="https://github.com/FHIR4DS/fhir4ds" \
      org.opencontainers.image.url="https://sql-on-fhir.org" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.vendor="FHIR4DS"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app

# curl exists only for HEALTHCHECK: the slim base ships no curl and no wget that
# can be relied on for an HTTP check with a status code.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer: only the files the package build reads, so editing a route
# does not invalidate the (slow) pip install.
COPY pyproject.toml README.md hatch_build.py hatch.toml ./
COPY fhir4ds ./fhir4ds
COPY deploy/docker/fhir4ds-serve/uvicorn-log.json ./uvicorn-log.json
# The bundled C++ extensions (fhir4ds/*/duckdb/extensions/) are built against
# one exact DuckDB version. An extension built for 1.5.5 refuses to load on
# 1.5.6, and the engine then SILENTLY falls back to Python UDFs — a behavioural
# change, not a warning. Pin the client to the ABI the bundle ships with.
ARG DUCKDB_VERSION=1.5.5
# The image is HF-capable (`[hf]` supplies huggingface-hub). The token is still
# run-time only: the backend reads HF_TOKEN from the environment.
RUN python -m pip install --no-cache-dir -e ".[serve,hf]" "duckdb==${DUCKDB_VERSION}"

# Non-root from here on. The image carries no pre-existing volume whose
# ownership would need migrating; mounted data is read-only and needs no HOME.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin fhir4ds
USER fhir4ds
WORKDIR /home/fhir4ds

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://127.0.0.1:7860/health || exit 1

# exec form, no shell: SIGTERM reaches uvicorn directly, which shuts down the
# server and exits cleanly (docker stop). `python -m fhir4ds.serve` instead of
# the `fhir4ds` console script: that script imports every subcommand, and the
# dqm one needs pandas, which this [serve]-only image deliberately omits.
CMD ["python", "-m", "fhir4ds.serve", "--host", "0.0.0.0", "--port", "7860", \
     "--data-root", "/data", "--log-config", "/app/uvicorn-log.json"]

# fhir4ds CLI

The `fhir4ds.cli` package provides the installed `fhir4ds` command.

```bash
fhir4ds --help
fhir4ds dqm --help
```

## Commands

### `fhir4ds dqm`

Digital Quality Measure batch evaluation.

```bash
fhir4ds dqm validate --config dqm-run.json
fhir4ds dqm inspect --config dqm-run.json
fhir4ds dqm run --config dqm-run.json
```

HAPI PostgreSQL materialization:

```bash
fhir4ds dqm hapi install --connection postgresql://hapi:hapi@localhost:15432/hapi
fhir4ds dqm hapi sync-config --config hapi-dqm.yaml
fhir4ds dqm hapi process-queue --config hapi-dqm.yaml --limit 100
fhir4ds dqm hapi listen --config hapi-dqm.yaml
```

The DQM command also supports a single-measure flag-based workflow:

```bash
fhir4ds dqm run \
  --measure ./measures/Measure-CMS124.json \
  --cql ./cql/CMS124FHIR.cql \
  --library-dir ./cql \
  --source "./data/*.ndjson" \
  --source-type filesystem \
  --source-format ndjson \
  --valuesets ./valuesets \
  --period 2025-01-01:2025-12-31 \
  --audit-mode population \
  --measure-reports both \
  --definitions all \
  --definition-format json \
  --output ./dqm-output
```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Command succeeded. |
| `1` | Validation failed or one or more measure runs failed. |
| `2` | Command-line or config input was invalid. |

## Development

Run the CLI tests:

```bash
python3 -m pytest fhir4ds/cli/tests -q
```

The package entry point is configured in `pyproject.toml`:

```toml
[project.scripts]
fhir4ds = "fhir4ds.cli.main:main"
```

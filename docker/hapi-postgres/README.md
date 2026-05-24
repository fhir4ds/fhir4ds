# HAPI FHIR PostgreSQL Dev Stack

Disposable local stack for testing `HapiPostgresSource`.

```bash
cd docker/hapi-postgres
docker compose up -d
```

Endpoints:

- HAPI FHIR: `http://localhost:18080/fhir`
- PostgreSQL: `postgresql://hapi:hapi@localhost:15432/hapi`

Smoke test:

```bash
curl -fsS -X POST http://localhost:18080/fhir/Patient \
  -H 'Content-Type: application/fhir+json' \
  --data '{"resourceType":"Patient","active":true,"name":[{"family":"FHIR4DS"}]}'

python3 - <<'PY'
import duckdb
from fhir4ds.sources import HapiPostgresSource

con = duckdb.connect(":memory:")
source = HapiPostgresSource("postgresql://hapi:hapi@localhost:15432/hapi")
source.register(con)
print(con.execute("select id, resourceType, patient_ref from resources").fetchall())
source.unregister(con)
PY
```

Materialization setup:

```bash
python3 -m pip install "psycopg[binary]>=3.1"

fhir4ds dqm hapi install \
  --config docker/hapi-postgres/hapi-materialization.example.yaml

fhir4ds dqm hapi sync-config \
  --config docker/hapi-postgres/hapi-materialization.example.yaml

fhir4ds dqm hapi process-queue \
  --config docker/hapi-postgres/hapi-materialization.example.yaml

fhir4ds dqm hapi status \
  --config docker/hapi-postgres/hapi-materialization.example.yaml
```

`install` creates FHIR4DS-owned queue/result tables, the decoded current-resource
view, and HAPI triggers. The triggers enqueue patient IDs and send
`LISTEN/NOTIFY` wake-up messages; measure calculation runs only in the FHIR4DS
worker.

Run the packaged worker container:

```bash
docker compose --profile worker up --build worker
```

The worker image installs `fhir4ds-v2[hapi]`, including `psycopg[binary]`. The
compose profile uses the internal PostgreSQL hostname `postgres` and mounts the
repo read-only at `/workspace` for local measure/config paths.

Load a small 2025 eCQM fixture into HAPI:

```bash
python3 scripts/hapi/load_2025_measure.py \
  --measure CMS122 \
  --base-url http://localhost:18080/fhir \
  --limit-patients 1
```

Or run the automated end-to-end smoke:

```bash
python3 scripts/hapi/smoke_2025_materialization.py \
  --measure CMS122 \
  --limit-patients 1
```

The smoke runner also accepts repeated or comma-separated measures and verifies
that each configured measure persists a result row for each loaded patient:

```bash
python3 scripts/hapi/smoke_2025_materialization.py \
  --measure CMS122,CMS124,CMS130 \
  --limit-patients 2
```

For a broader artifact smoke without listing IDs manually:

```bash
python3 scripts/hapi/smoke_2025_materialization.py \
  --all-measures \
  --limit-measures 5 \
  --limit-patients 1 \
  --artifact-source hapi \
  --persist-measure-report
```

By default, measure artifacts are read from local files while patient data is
analyzed in HAPI PostgreSQL. To verify HAPI-hosted Measure, Library, and
ValueSet artifacts, use:

```bash
python3 scripts/hapi/smoke_2025_materialization.py \
  --measure CMS122 \
  --limit-patients 1 \
  --artifact-source hapi
```

For worker configuration, set `artifacts.source: hapi` and give each measure an
`artifact_ref` matching the HAPI Measure id, canonical URL, or `Measure/<id>`.
ValueSets declared by the primary CQL library and included libraries are
resolved from HAPI, including `version` qualifiers. Each ValueSet must contain
an expansion, direct compose concepts, or be expandable by HAPI. If an
unversioned declaration matches multiple HAPI ValueSet resources, the worker
tries candidate versions newest-first and uses the newest loadable or expandable
ValueSet; set `hapi.valueset_version_policy: error` to require an explicit CQL
version or `canonical|version`.

Authenticated HAPI servers can be configured with static headers, a bearer
token, and a request timeout:

```yaml
hapi:
  base_url: https://hapi.example/fhir
  timeout_seconds: 30
  bearer_token: replace-with-token
  headers:
    X-Tenant: quality
```

To verify generated individual `MeasureReport` JSON persistence, add
`--persist-measure-report`. Reports are stored on the active result row and in
`fhir4ds_measure_report` for direct querying/history. To also publish those
reports back to HAPI through FHIR REST, add `--publish-measure-report-to-hapi`;
generated reports use deterministic `fhir4ds-` IDs and are tagged so the
PostgreSQL trigger does not enqueue them as new patient changes.

Cleanup:

```bash
docker compose down -v
```

The compose file uses `hapiproject/hapi:latest` because HAPI's GitHub release
tags do not always map directly to Docker image tags. Pin a verified image tag
before using this stack in repeatable CI.

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
  --connection postgresql://hapi:hapi@localhost:15432/hapi

fhir4ds dqm hapi sync-config \
  --config docker/hapi-postgres/hapi-materialization.example.yaml

fhir4ds dqm hapi process-queue \
  --config docker/hapi-postgres/hapi-materialization.example.yaml
```

`install` creates FHIR4DS-owned queue/result tables and HAPI triggers. The
triggers enqueue patient IDs and send `LISTEN/NOTIFY` wake-up messages; measure
calculation runs only in the FHIR4DS worker.

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

Cleanup:

```bash
docker compose down -v
```

The compose file uses `hapiproject/hapi:latest` because HAPI's GitHub release
tags do not always map directly to Docker image tags. Pin a verified image tag
before using this stack in repeatable CI.

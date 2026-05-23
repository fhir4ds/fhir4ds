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

Cleanup:

```bash
docker compose down -v
```

The compose file uses `hapiproject/hapi:latest` because HAPI's GitHub release
tags do not always map directly to Docker image tags. Pin a verified image tag
before using this stack in repeatable CI.

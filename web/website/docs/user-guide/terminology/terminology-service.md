---
id: terminology-service
title: Terminology Service
sidebar_label: Terminology Service
---

# Terminology Service

The terminology service abstraction (`fhir4ds.cql.terminology`) is the seam between fhir4ds and any FHIR R4 terminology provider. By default it ships **disabled** — `import fhir4ds` pulls no terminology dependencies. Opt in via an install extra and an environment variable, and the CQL translator, the auto-coder, and the closure-table builder all start resolving ValueSets and subsumption relationships against your chosen terminology server.

The reference backend is [medterm4ds](https://github.com/joelmontavon/medterm4ds) — a UMLS-backed FHIR R4 terminology server with `$expand`, `$lookup`, `$validate-code`, `$translate`, `$subsumes`, `$closure`, plus a custom `$search` operation for lexical/hybrid/semantic concept discovery.

## 1. Install

```bash
pip install 'fhir4ds-v2[terminology]'
```

The extra pulls `httpx>=0.24` and `medterm4ds>=0.0.1`. fhir4ds itself never imports either at module load — both are imported lazily inside the factory when you opt into a non-disabled mode.

## 2. Configuration

The factory `fhir4ds.cql.terminology.factory.get_terminology_endpoint(config=None)` reads from explicit config or environment variables:

| Env var | Purpose | Default |
|---|---|---|
| `FHIR4DS_TERMINOLOGY_MODE` | `disabled` \| `http` \| `in_process` | `disabled` |
| `FHIR4DS_TERMINOLOGY_URL` | FHIR root URL for HTTP mode (e.g. `http://127.0.0.1:8001/fhir`) | — |
| `FHIR4DS_TERMINOLOGY_TIMEOUT` | HTTP timeout in seconds | `5.0` |
| `FHIR4DS_TERMINOLOGY_DB` | Path to medterm4ds DuckDB file (in_process mode) | medterm4ds default |
| `FHIR4DS_TERMINOLOGY_SEARCH_INDEX_DIR` | Prebuilt search-index directory (in_process mode) | — |
| `FHIR4DS_TERMINOLOGY_PROBE` | `true` to log a startup health probe | `false` |

Env vars are read **lazily inside the factory body**, not at module import. Passing an explicit `TerminologyConfig` overrides env vars.

```python
from fhir4ds.cql.terminology import (
    TerminologyConfig,
    get_terminology_endpoint,
)

# Via explicit config
endpoint = get_terminology_endpoint(
    TerminologyConfig(
        mode="http",
        url="http://127.0.0.1:8001/fhir",
        timeout_seconds=10.0,
    )
)

# Or via env vars: FHIR4DS_TERMINOLOGY_MODE=http FHIR4DS_TERMINOLOGY_URL=...
endpoint = get_terminology_endpoint()
```

## 3. HTTP mode

HTTP mode is the right choice when you already run a terminology server (medterm4ds sidecar, HL7 FHIR server, Aperture, etc.). The adapter speaks standard FHIR R4 operations: `$expand`, `$expand` with `valueSet` body (intensional), `$lookup`, `$subsumes`, `$closure`, plus medterm4ds's custom `$search`.

```python
from fhir4ds.cql.terminology import TerminologyConfig, get_terminology_endpoint

endpoint = get_terminology_endpoint(
    TerminologyConfig(
        mode="http",
        url="http://127.0.0.1:8001/fhir",
    )
)

# Expand a ValueSet by canonical URL (with fhir_vs shorthand)
refs = endpoint.expand("http://snomed.info/sct?fhir_vs=isa/73211009")
# → [CodeRef(system="http://snomed.info/sct", code="73211009", display="Diabetes mellitus (disorder)"), ...]
```

## 4. In-process mode

In-process mode embeds medterm4ds directly — no HTTP hop. The factory calls `medterm4ds.connect(db_path=...)` to build a `Terminology` facade whose `.engine` is a `DiscoveryEngine` we can drive.

```python
from fhir4ds.cql.terminology import TerminologyConfig, get_terminology_endpoint

endpoint = get_terminology_endpoint(
    TerminologyConfig(
        mode="in_process",
        medterm4ds_db_path="/path/to/lookup.duckdb",
    )
)

# Same surface as HTTP mode
refs = endpoint.expand("http://snomed.info/sct?fhir_vs=isa/73211009")
results = endpoint.search_text("diabetes", category="condition", mode="hybrid")
```

**Known limitation:** `expand_intensional` is HTTP-only on the published medterm4ds 0.0.1 wheel — there is no programmatic entry point. The in-process adapter logs a WARNING and returns `[]`; if you need intensional ValueSet expansion, switch this endpoint to HTTP mode.

## 5. Endpoint surface

All three modes (`disabled` returns `None`) expose the same protocol (`fhir4ds.cql.terminology.endpoint.TerminologyEndpoint`):

| Method | Returns | Description |
|---|---|---|
| `expand(valueset_url)` | `list[CodeRef]` | Expand a ValueSet canonical URL (supports `fhir_vs` shorthand and filter forms). |
| `expand_intensional(value_set)` | `list[CodeRef]` | Expand an intensional ValueSet (compose-walk). HTTP-only on published medterm4ds. |
| `search_text(query, category, *, mode)` | `list[SearchResult]` | Lexical/semantic/hybrid search over concept names. |
| `search_batch(queries, *, mode)` | `list[list[SearchResult]]` | Batched `search_text`. |
| `is_healthy()` | `bool` | Probe the underlying engine / server without raising. Never raises. |

## 6. Circuit breaker

Both adapters ship with a per-instance circuit breaker. After `breaker_threshold` consecutive failures (default 5), subsequent calls short-circuit to `[]` for `breaker_cooldown_seconds` (default 60.0). A successful call resets the counter. The breaker is not thread-safe — if you share an endpoint across threads, wrap it in an external lock.

```python
from fhir4ds.cql.terminology.in_process_adapter import InProcessTerminologyEndpoint

endpoint = InProcessTerminologyEndpoint(
    breaker_threshold=10,
    breaker_cooldown_seconds=120.0,
)
```

The "not supported" path on `expand_intensional` (in-process mode, published medterm4ds 0.0.1) intentionally **does not** trip the breaker — it's a permanent gap rather than a transient failure, and tripping would collateral-damage `expand` and `search_text`.

## 7. System URL normalization

medterm4ds returns source mnemonics from UMLS (`SNOMEDCT_US`, `RXNORM`, `LNC`, `ICD10CM`, `CPT`). fhir4ds expands these to their FHIR canonical URLs before returning `CodeRef`s, so downstream joins against `valueset_codes` rows that use `http://snomed.info/sct` succeed:

| UMLS mnemonic | FHIR canonical URL |
|---|---|
| `SNOMEDCT_US` | `http://snomed.info/sct` |
| `RXNORM` | `http://www.nlm.nih.gov/research/umls/rxnorm` |
| `LNC` | `http://loinc.org` |
| `ICD10CM` | `http://hl7.org/fhir/sid/icd-10-cm` |
| `CPT` | `http://www.ama-assn.org/go/cpt` |

The map lives in `fhir4ds.cql.terminology.system_mappings.SOURCE_MNEMONIC_TO_URL`. A second pass through `SystemResolver.normalize` reduces OID and SNOMED module URL variants (`http://snomed.info/sct/731000124108`) to their canonical base.

## 8. Wiring it into the loader and the translator

Once you have an endpoint, pass it through the loader and the CQL evaluator:

```python
import fhir4ds
from fhir4ds.cql import FHIRDataLoader
from fhir4ds.cql.terminology import TerminologyConfig, get_terminology_endpoint

con = fhir4ds.create_connection()
endpoint = get_terminology_endpoint(TerminologyConfig(mode="http", url="http://127.0.0.1:8001/fhir"))

loader = FHIRDataLoader(con, terminology_endpoint=endpoint)
loader.load_ndjson("conditions.ndjson")

# CQL retrieves against [ValueSet: <canonical>] now resolve via the endpoint.
```

For auto-coding of text-only `CodeableConcept`s, see [Auto-Coding](./autocoding.md). For clinical-notes NER (deriving Conditions from free text), see [Notes Pipeline](./notes-pipeline.md).

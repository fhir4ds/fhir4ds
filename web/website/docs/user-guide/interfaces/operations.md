---
id: operations
title: Operations Layer
sidebar_label: Operations Layer
---

# Operations Layer

The operations layer (`fhir4ds.operations`) defines every user-facing engine
capability **once**, with typed, versioned result envelopes. All interfaces —
the [Python API](#python-usage), the [CLI](./cli), and the
[MCP server](./mcp) — are thin adapters over the same operations, so any
surface produces identical results for the same inputs.

## Capabilities (v1)

| Operation | Purpose |
|-----------|---------|
| `parse_cql` | Parse/validate CQL; library, definition, parameter, and include metadata |
| `translate_cql` | Emit the generated SQL for a library |
| `evaluate_library` | Evaluate populations; one row per patient |
| `run_tests` | Run declarative test cases (the `fhir4ds verify` core) |
| `fhirpath_eval` | Evaluate a FHIRPath expression against one resource |
| `load_dataset` | Load inline resources or NDJSON/Bundle files; per-type counts |
| `explain_patient` | Audit-evidence drill-in: why a patient is in/out of each population |

## Envelopes

Every operation returns a frozen dataclass carrying shared fields:

| Field | Meaning |
|-------|---------|
| `schema` | Envelope contract version (currently `1`) |
| `ok` | Execution succeeded — the envelope is trustworthy |
| `passed` | Test assertions held (`run_tests` only; `None` elsewhere) |
| `diagnostics` | Typed diagnostic list (may be non-empty even when `ok`) |

`ok` and `passed` are deliberately distinct: a run can execute cleanly
(`ok: true`) while a test case fails (`passed: false`). Agents should branch
on `passed` for red/green and on `ok` for retryable execution failures.

## Diagnostics

Diagnostics are the machine contract. Each carries:

- `code` — one of `parse_error`, `translation_error`, `evaluation_error`,
  `input_error`, `dataset_error`, `not_found`, `unsupported_feature`
  (`timeout` is reserved for future use);
- `severity` — `error`, `warning`, or `info`;
- `message` — stable human-readable text;
- `location` — structured `start_line`/`start_column` (+ optional end and
  library) lifted from engine parser positions, ready for editor squiggles;
- `data` — structured engine fields verbatim (`expected`/`found` from parse
  errors, `symbol`/`expected_type`/`actual_type` from semantic errors, and so
  on), so tools never regex error strings.

## Library resolution

`include` statements resolve through one chain, applied identically by every
adapter:

1. **Inline libraries** supplied by the caller (explicit wins — an inline
   library always overrides a bundled library of the same name);
2. **Bundled standards** shipped in the wheel (`FHIRHelpers`, `QICoreCommon`,
   `Status` under `fhir4ds/cql/resources/cql/`), read via
   `importlib.resources` — this also works in Pyodide/WASM builds;
3. **Adapter sources** (CLI `--include-dir`, MCP session cache);
4. otherwise a typed `not_found` diagnostic naming the missing alias and the
   tiers consulted — never a silent miss.

## Python usage

```python
from fhir4ds import create_connection
from fhir4ds.operations import (
    LibraryText, DatasetSpec, tests_input_from_dict,
    run_tests,
)

main = LibraryText(name="Simple", text="""
library Simple version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.4.000' called FHIRHelpers
define "Initial Population":
  exists([Patient] P where P.gender = 'female')
""")

dataset = DatasetSpec(resources=[
    {"resourceType": "Patient", "id": "p1", "gender": "female"},
    {"resourceType": "Patient", "id": "p2", "gender": "male"},
])

cases = tests_input_from_dict({
    "schema": 1,
    "cases": [
        {"patient": "p1", "population": "Initial Population", "expect": True},
        {"patient": "p2", "population": "Initial Population", "expect": False},
    ],
})

conn = create_connection()
result = run_tests([main], main, dataset, cases, conn)
print(result.to_dict())
```

Operations are stateless functions over `(inputs, conn)`: supply your own
DuckDB connection (`fhir4ds.create_connection()` registers the engine's
UDFs), pass `dataset=None` to evaluate against data already loaded on the
connection.

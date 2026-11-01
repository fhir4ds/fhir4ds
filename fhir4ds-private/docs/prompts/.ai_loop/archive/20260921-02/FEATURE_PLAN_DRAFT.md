# FEATURE PLAN DRAFT — Operations Layer + verify CLI + MCP Server (v1 draft)

Status: v1 DRAFT (Feature Designer; pre-self-audit)
Mandate: `.ai_loop/USER_DIRECTIVES.md` (operations-layer groundwork cycle)
Design inputs: `docs/architecture/plans/FEATURE_AGENTIC_VERIFY_MCP.md`,
`docs/architecture/plans/FEATURE_CQL_STUDIO_LITE.md` §2a.

## 1. Objective

Build the shared operations layer that both FDDs depend on, and the first
two thin adapters on top of it:

1. **`fhir4ds/operations/`** — capabilities defined once, typed versioned
   envelopes (`schema: 1`), typed diagnostics taxonomy, connection/dataset
   injection model.
2. **`fhir4ds verify` CLI** (`fhir4ds/cli/verify.py`) — one-shot
   library-vs-dataset evaluation with declarative test cases; JSON
   envelope to stdout; agent-usable exit codes.
3. **`fhir4ds-mcp` stdio server** (`fhir4ds/mcp/`, `[mcp]` extra) — the
   seven v1 capabilities as MCP tools mapping 1:1 onto operations.

The capability-matrix test runs one fixture through CLI subprocess and
in-process MCP client and asserts identical envelopes.

## 2. Spec Alignment

- MCP: Model Context Protocol stdio transport (JSON-RPC 2.0); tools per
  MCP spec `tools/call`, `tools/list`. Client-tested via the official
  `mcp` Python SDK (FastMCP server + client session over anystdio
  memory transport).
- Envelope versioning: `"schema": 1` per both FDDs §2a.
- CLI conventions: repo `fhir4ds/cli/AGENTS.md` (exit codes 0/1/2,
  stdout-is-contract, dataclass config translation).
- Test-case schema: FEATURE_AGENTIC_VERIFY_MCP.md §7 (patients ×
  population|define × expect), `"schema": 1`.
- Engine surfaces (unchanged): `parse_cql`, `translate_library_to_sql`,
  `evaluate_measure` (audit_mode), `FHIRDataLoader`,
  `MeasureEvaluator`/`AuditEngine` evidence, `$cql` facade typed-error
  precedent (`CQLErrorCategory`).

## 3. Architecture

### 3.1 Module layout

```
fhir4ds/operations/
  __init__.py        # public exports (capability functions)
  envelopes.py       # dataclasses: Envelope, Diagnostics, codes
  dataset.py         # DatasetSpec resolution -> FHIRDataLoader calls
  capabilities/
    __init__.py
    parse.py         # parse_cql          -> ParseResult
    translate.py     # translate_cql      -> TranslateResult (SQL text)
    evaluate.py      # evaluate_library   -> EvaluateResult (rows+summary)
    run_tests.py     # run_tests          -> VerifyEnvelope
    fhirpath.py      # fhirpath_eval      -> FhirpathResult
    dataset_ops.py   # load_dataset       -> DatasetResult (stats)
    explain.py       # explain_patient    -> EvidenceResult
  errors.py          # OperationError(code, message, detail, cause)
```

### 3.2 Envelope shape (schema: 1)

```python
@dataclass(frozen=True)
class Diagnostics:
    code: DiagnosticCode   # enum, below
    message: str           # stable, human-readable
    detail: str | None     # line/col, define name, SQL excerpt...

@dataclass(frozen=True)
class Envelope:            # base; capability payloads extend
    schema: int = 1
    ok: bool = True
    diagnostics: tuple[Diagnostics, ...] = ()
```

Diagnostic codes (v1 enum, string values):
`PARSE_ERROR`, `TRANSLATION_ERROR`, `EVALUATION_ERROR`, `INPUT_ERROR`,
`TIMEOUT`, `UNSUPPORTED_FEATURE`, `NOT_FOUND`, `DATASET_ERROR`.

Mapping table from typed Python errors (design constraint 4):
`ParseError/LexerError → PARSE_ERROR`; `TranslationError →
TRANSLATION_ERROR`; `CQLFacadeError(category) → same-named code where
1:1, else EVALUATION_ERROR`; `ValueError/TypeError/FileNotFoundError/
JSONDecodeError at input boundary → INPUT_ERROR`; `duckdb.Error →
EVALUATION_ERROR` (detail carries the DuckDB message; catalog errors
indicating missing UDF registration stay raw per 0.0.12 doctrine);
timeout guard → `TIMEOUT`.

### 3.3 Capability signatures (v1, 7 capabilities)

```python
def parse_cql(cql_text: str) -> ParseResult
def translate_cql(libs: list[LibraryText], main: str, *, parameters=None) -> TranslateResult
def evaluate_library(libs, dataset: DatasetSpec, parameters, output_columns, conn) -> EvaluateResult
def run_tests(libs, dataset, cases: list[TestCase], parameters, conn) -> VerifyEnvelope
def fhirpath_eval(expression: str, resource: dict) -> FhirpathResult
def load_dataset(dataset: DatasetSpec, conn) -> DatasetResult
def explain_patient(libs, dataset, patient_id, parameters, conn) -> EvidenceResult
```

`LibraryText` = `{name, text, version?}` (inline text; includes resolved
against the list). `DatasetSpec` = inline `resources[]` OR file paths
(`.ndjson` / `.json` bundle) OR valueset file paths — validated first,
then resolved through `FHIRDataLoader` on the caller-supplied connection.

### 3.4 Connection / dataset injection model

Operations take `conn` + `DatasetSpec`; they never open files except
through declared paths, never hold module-level state. The MCP adapter
owns one DuckDB connection + the dataset-handle map (verify FDD D2);
the CLI opens its own connection per invocation. No session state in
operations core (binding constraint 2).

### 3.5 Adapters

**CLI (`fhir4ds/cli/verify.py`):**
```
fhir4ds verify --library MEASURE.cql [--include-dir DIR ...]
               [--data DATA.ndjson | --data-dir DIR | --data FILE.json ...]
               [--valueset FILE.json ...] [--tests cases.json]
               [--parameters JSON] [--output-columns MAP]
               [--format json|text] [--emit-sql] [--timeout-seconds N]
```
argv → dataclasses → operations → envelope → stdout JSON; exit codes
0/1/2. Test-case evaluation: evaluate once, check each case against the
patient's row (no per-case re-eval).

**MCP (`fhir4ds/mcp/server.py`):** FastMCP server, stdio only. Tools map
1:1 to operations; `load_dataset` returns a handle from the adapter's
map; subsequent tools accept `dataset: {handle|resources|paths}`.
Inline resources payload capped (5MB) with typed INPUT_ERROR. Tool errors
return `isError: true` content with the diagnostics JSON (never
tracebacks). Entry point `fhir4ds-mcp = fhir4ds.mcp.server:main` in
`[project.scripts]`; `mcp` SDK behind `[mcp]` optional extra.

### 3.6 Capability-matrix test

Shared fixture (one small library + NDJSON + cases file) executed via:
(1) CLI subprocess (`fhir4ds.cli.main:main` argv) capturing stdout JSON;
(2) in-process MCP client (FastMCP memory transport) calling
`run_tests`. Normalize (drop transport framing/timing) → assert
identical envelope dicts (ok, diagnostics codes, summary, tests
pass/fail per patient).

## 4. Implementation Plan (units)

1. **U1 — envelopes + errors + dataset spec.** Dataclasses, codes,
   mapping table, DatasetSpec validation. Unit tests.
2. **U2 — parse + translate capabilities.** Wire to existing engine
   APIs; diagnostics from typed errors. Unit tests.
3. **U3 — dataset_ops + evaluate + run_tests.** FHIRDataLoader
   orchestration; evaluate once/check cases; VerifyEnvelope. Unit tests.
4. **U4 — fhirpath_eval + explain_patient.** fhirpath evaluation via
   `fhir4ds.fhirpath` engine; audit evidence extraction (evaluator with
   audit_mode="full", filter to patient). Unit tests.
5. **U5 — verify CLI.** Parser, envelope→stdout, exit codes. CLI tests
   (patterns from dqm tests).
6. **U6 — MCP server.** FastMCP tools, handle map, payload cap, error
   surfaces, entry point + `[mcp]` extra. Tool tests via in-process
   client.
7. **U7 — capability-matrix test + README client configs.** Parity
   legs; docs snippets (Claude Desktop / opencode / Cursor).

## 5. Test Strategy

- Unit tests per capability (new `fhir4ds/operations/tests/`),
  CLI tests in `fhir4ds/cli/tests/`, MCP tests in `fhir4ds/mcp/tests/`.
- Matrix test at `fhir4ds/operations/tests/test_capability_matrix.py`.
- Malformed-input battery per adapter: bad CQL, bad JSON, missing files,
  unknown define/patient → typed diagnostics, no tracebacks; CLI exit
  codes 0/1/2.
- Gates per unit: master conformance 2832/2832 untouched; full pytest
  trees green (cli, cql, dqm, sources, viewdef); no engine module
  modified (enforced by review, not runtime).

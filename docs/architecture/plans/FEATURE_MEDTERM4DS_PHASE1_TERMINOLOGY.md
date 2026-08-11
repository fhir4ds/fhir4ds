# FEATURE DESIGN — medterm4ds Phase 1: Terminology Abstraction (Foundation)

**Status:** APPROVED (pre-approved via `USER_DIRECTIVES.md`; architecture self-audit complete)
**Source plan:** `fhir4ds-private/docs/plans/medterm4ds-integration.md` (Phase 1 section)
**Verified against codebase:** 2026-07-03 (post spec-compliance campaign, branch `dev`)
**Target version:** 0.0.11
**Scope:** Phase 1 ONLY. Phases 2–4 are deferred to later FDDs.

---

## 1. Objective

Add a terminology service abstraction to `fhir4ds` so ValueSet URLs which are
*not* resolvable from local `DependencyResolver` file paths can be expanded on
demand from an external terminology service (default: medterm4ds). The
abstraction supports two interchangeable adapters (HTTP sidecar, in-process
library) behind a single `TerminologyEndpoint` protocol, plus an env-driven
factory. The integration is fully opt-in: with `terminology_endpoint=None`
(default), existing behavior is byte-for-byte unchanged.

**Phase 1 success criterion:** A caller can construct
`DependencyResolver(paths=[...], terminology_endpoint=get_terminology_endpoint())`
and have ValueSet URLs missing from local files transparently expanded from
medterm4ds (HTTP or in-process). Plumbing the kwarg through `evaluate_measure()`
and the FHIR `$cql` facade is **deferred to a Phase 1.5 follow-on** (see §7).

---

## 2. Spec Alignment

### 2a. FHIR `$cql` operation — `terminologyEndpoint` parameter

HL7 Clinical Reasoning `[$cql](https://hl7.org/fhir/R4/operation-cqf-cql.html)`
operation defines a `terminologyEndpoint` parameter (type `Endpoint`, 0..1) that
the CQL execution engine MUST use as the terminology service for ValueSet
expansion. Today `fhir4ds` lists this name in `_UNSUPPORTED_TOP_LEVEL` at
`fhir4ds/cql/fhir_server/parameters.py:23-31`. **Phase 1 does not change the
facade** — it adds the in-process abstraction only. Removing the name from
`_UNSUPPORTED_TOP_LEVEL` is a Phase 1.5 follow-on (§7).

### 2b. FHIR R4 `ValueSet $expand`

HL7 `[ValueSet $expand](https://hl7.org/fhir/R4/valueset-operation-expand.html)`.
The abstraction supports three expansion modes medterm4ds already exposes at
`src/medterm4ds/apps/fhir_api.py` (verified at `_do_expand`, line 421):
- **URL-based canonical** (`url=http://...&filter=...`) — GET `/fhir/ValueSet/$expand`
- **Intensional** (POST a ValueSet resource with `compose.include[].filter[op=is-a|descendant-of]`)
- **`fhir_vs` shorthand** (e.g. `http://snomed.info/sct?fhir_vs=isa/73211009`) — handled by URL mode

Return shape is normalized to FHIR R4 `ValueSet.expansion.contains[]` records
and exposed as `CodeRef` dataclasses.

### 2c. CQL 1.5 spec — terminology integration

CQL `[ValueSets and Codes](https://cql.hl7.org/02-authorsguide.html#valuesets)`:
a CQL `valueset "X" '<url>'` reference is resolved at translation time against
the in-scope library context. The spec leaves the *resolution strategy* to the
implementation (local files, terminology service, or hybrid). Phase 1 implements
the **hybrid** strategy: local first, terminology endpoint as fallback. This
matches the spec intent without changing translator semantics.

### 2d. `$search` (medterm4ds extension)

medterm4ds exposes a custom `$search` operation (GET/POST
`/fhir/CodeSystem/$search`) that returns ranked `SearchResult` records with
score and match-grade. This is **not** a FHIR R4 standard operation — it backs
the future auto-coding (Phase 2) and NER (Phase 4) pipelines. Phase 1 only
*exposes* the operation on the protocol; it is not consumed by
`DependencyResolver` fallback.

---

## 3. Architecture

### 3a. Integration point — `DependencyResolver`

Current codebase state (verified 2026-07-03):

| Path | Role |
|------|------|
| `fhir4ds/cql/dependency/resolver.py:332` | `resolve_valueset(url)` — exact-match dict lookup, no fallback |
| `fhir4ds/cql/dependency/types.py:60-75` | `ResolutionContext` carries `valuesets: Dict[str, ResolvedValueSet]` |
| `fhir4ds/cql/__init__.py:536` | `evaluate_measure_legacy` constructs resolver from `paths=[...]` |
| `fhir4ds/cql/loader/fhir_loader.py:560` | `load_valuesets()` writes resolved codes into DuckDB `valueset_codes` table consumed by the `fhirpath_in_valueset` UDF |

**Phase 1 change (additive only):**

1. `DependencyResolver.__init__` gains `terminology_endpoint: Optional[TerminologyEndpoint] = None` (forward-quoted, TYPE_CHECKING import — see §4.6).
2. `resolve_valueset()` wraps the existing lookup. If local lookup misses AND
   the endpoint is configured, call `endpoint.expand(url)`. If non-empty,
   synthesize a `ResolvedValueSet` with `source_path=None` and
   `provenance="terminology_endpoint"`.
3. **Failure-mode scoping (per INV-8):** Inside `DependencyResolver.resolve_valueset`,
   endpoint exceptions are caught and degraded to `None` with a WARNING log.
   This graceful-degradation contract applies *only* to this fallback path.
   Direct callers of `TerminologyEndpoint.expand()` (e.g. the Phase 3 closure
   loader) MUST let exceptions propagate — silent swallowing there would mask
   real bugs.

### 3b. New subpackage: `fhir4ds/cql/terminology/`

```
fhir4ds/cql/terminology/
├── __init__.py          # Public re-exports ONLY (no adapter imports here)
├── types.py             # CodeRef, SearchResult, TerminologyConfig dataclasses
├── endpoint.py          # TerminologyEndpoint Protocol
├── http_adapter.py      # HTTPTerminologyEndpoint (httpx, optional)
├── in_process_adapter.py# InProcessTerminologyEndpoint (medterm4ds, optional)
└── factory.py           # get_terminology_endpoint(config=None) -> TerminologyEndpoint | None
```

`__init__.py` exports `TerminologyEndpoint`, `CodeRef`, `SearchResult`,
`TerminologyConfig`, and `get_terminology_endpoint`. Adapter classes are
imported *inside* the factory function body (lazy), so
`import fhir4ds.cql.terminology` never imports `httpx` or `medterm4ds`. This
is the **non-negotiable INV-1 guarantee**.

### 3c. System URI normalization (shared)

Both adapters normalize returned `CodeRef.system` values through
`fhir4ds/cql/duckdb/udf/system_resolver.py:SystemResolver.normalize()` before
returning. Critical: medterm4ds returns SNOMED US-edition module URLs like
`http://snomed.info/sct/731000124108`; without normalization these would fail
to join with rows produced by `loader.load_valuesets()`.

### 3d. Return-type contract

Endpoint protocol methods return bounded `list[CodeRef]` (not generators).
This guarantees Phase 3's closure-table loader can iterate the result multiple
times without re-invoking the endpoint.

---

## 4. Implementation Plan (file-level tasks)

### 4.1 Create `fhir4ds/cql/terminology/types.py`

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CodeRef:
    system: str          # Canonical form (already normalized via SystemResolver)
    code: str
    display: str | None = None

@dataclass(frozen=True)
class SearchResult(CodeRef):
    score: float
    match_grade: str          # "certain" | "probable" | "ambiguous" | "no-match"
    search_mode: str          # "lexical" | "hybrid" | "semantic"
    index_version: str | None = None

@dataclass(frozen=True)
class TerminologyConfig:
    mode: str = "disabled"                       # "http" | "in_process" | "disabled"
    url: str | None = None                       # base URL for HTTP mode
    timeout_seconds: float = 5.0                 # bounded HTTP timeout (INV-6)
    medterm4ds_db_path: str | None = None        # for in_process mode
    search_index_dir: str | None = None          # for in_process mode
```

### 4.2 Create `fhir4ds/cql/terminology/endpoint.py`

```python
from __future__ import annotations
from typing import Protocol
from .types import CodeRef, SearchResult

class TerminologyEndpoint(Protocol):
    """Structural protocol — test doubles need not inherit."""
    def expand(self, valueset_url: str) -> list[CodeRef]: ...
    def expand_intensional(self, value_set: dict) -> list[CodeRef]: ...
    def search_text(self, query: str, category: str, *, mode: str = "hybrid") -> list[SearchResult]: ...
    def search_batch(self, queries: list[tuple[str, str]], *, mode: str = "hybrid") -> list[list[SearchResult]]: ...
```

### 4.3 Create `fhir4ds/cql/terminology/http_adapter.py`

- `httpx` imported at module top — module is only imported by factory.
- All four methods call medterm4ds FHIR endpoints:
  - `expand(url)` → GET `{base}/fhir/ValueSet/$expand?url=...`
  - `expand_intensional(value_set)` → POST `{base}/fhir/ValueSet/$expand` with body `value_set`
  - `search_text(query, category, mode)` → GET `{base}/fhir/CodeSystem/$search`
  - `search_batch(queries, mode)` → sequential calls to `search_text` (no batch endpoint exists yet)
- Every call uses `httpx.Client(timeout=self._timeout)` — **no infinite hangs** (INV-6).
  Use keyword form; never `timeout=None`.
- Response parsing walks `expansion.contains[]` → `CodeRef`, normalizing system via `SystemResolver.normalize()`.
- Network exceptions propagate to caller (factory's caller decides whether to degrade).

### 4.4 Create `fhir4ds/cql/terminology/in_process_adapter.py`

- `medterm4ds` imported lazily inside `__init__` (so module import is cheap and isolated).
- Holds a single shared `LocalDuckDBEngine` instance (constructed once per adapter).
- Maps:
  - `expand(url)` → medterm4ds `services.valueset.expand_valueset` (engineer: confirm exact public symbol at `/mnt/d/medterm4ds/src/medterm4ds/services/` at implementation time).
  - `expand_intensional(value_set)` → same service with intensional input.
  - `search_text(query, category, mode)` → `medterm4ds.services.discovery.search_names`.
  - `search_batch(queries, mode)` → `medterm4ds.services.discovery.search_names_dataframe` (batch-first; verify in `services/discovery/__init__.py`).
- Normalize `CodeRef.system` via `SystemResolver.normalize()` before returning.

### 4.5 Create `fhir4ds/cql/terminology/factory.py`

```python
from __future__ import annotations
import os
from typing import Optional
from .endpoint import TerminologyEndpoint
from .types import TerminologyConfig

def get_terminology_endpoint(config: Optional[TerminologyConfig] = None) -> Optional[TerminologyEndpoint]:
    """Build a TerminologyEndpoint from config or environment variables.

    Returns None when mode is "disabled" (default) — preserves zero-dep
    behavior. Reads env vars lazily here, never at module import.
    """
    cfg = config or _config_from_env()
    if cfg.mode == "disabled":
        return None
    if cfg.mode == "http":
        if not cfg.url:
            raise ValueError("FHIR4DS_TERMINOLOGY_URL is required when mode=http")
        from .http_adapter import HTTPTerminologyEndpoint  # lazy import (INV-1, INV-3)
        try:
            import httpx  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "httpx is required for HTTP terminology mode. "
                "Install with: pip install 'fhir4ds-v2[terminology]'"
            ) from e
        return HTTPTerminologyEndpoint(cfg.url, cfg.timeout_seconds)
    if cfg.mode == "in_process":
        from .in_process_adapter import InProcessTerminologyEndpoint  # lazy
        try:
            import medterm4ds  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "medterm4ds is required for in-process terminology mode. "
                "Install medterm4ds alongside fhir4ds-v2[terminology]."
            ) from e
        return InProcessTerminologyEndpoint(cfg.medterm4ds_db_path, cfg.search_index_dir)
    raise ValueError(f"Unknown terminology mode: {cfg.mode}")

def _config_from_env() -> TerminologyConfig:
    return TerminologyConfig(
        mode=os.getenv("FHIR4DS_TERMINOLOGY_MODE", "disabled"),
        url=os.getenv("FHIR4DS_TERMINOLOGY_URL"),
        timeout_seconds=float(os.getenv("FHIR4DS_TERMINOLOGY_TIMEOUT", "5.0")),
        medterm4ds_db_path=os.getenv("FHIR4DS_TERMINOLOGY_DB"),
        search_index_dir=os.getenv("FHIR4DS_TERMINOLOGY_SEARCH_INDEX_DIR"),
    )
```

### 4.6 Modify `fhir4ds/cql/dependency/resolver.py` (additive)

- Add a `TYPE_CHECKING` block at the top:
  ```python
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
      from ..terminology.endpoint import TerminologyEndpoint
  ```
- `__init__` signature gains:
  ```python
  terminology_endpoint: "Optional[TerminologyEndpoint]" = None,
  ```
  (forward-quoted — no runtime import; Protocol is structural).
- Store as `self._terminology_endpoint`.
- Wrap `resolve_valueset()` (line 332) in fallback logic (per §3a):
  ```python
  def resolve_valueset(self, url: str) -> Optional[ResolvedValueSet]:
      vs = self._valuesets.get(url)
      if vs is not None:
          return vs
      if self._terminology_endpoint is None:
          return None
      try:
          codes = self._terminology_endpoint.expand(url)
      except Exception as e:
          _logger.warning(
              "terminology endpoint expand failed for %s: %s", url, e
          )
          return None
      if not codes:
          return None
      return ResolvedValueSet(
          url=url,
          version=None,
          name=None,
          source_path=None,
          codes=[
              {"system": c.system, "code": c.code, "display": c.display}
              for c in codes
          ],
          provenance="terminology_endpoint",
      )
  ```

### 4.7 Modify `fhir4ds/cql/dependency/types.py`

- Add `provenance: str = "local_file"` field to `ResolvedValueSet` dataclass.
  Default preserves existing constructor calls (no breaking change).
- Make `source_path: Optional[Path]` (already optional in practice for endpoint
  resolution; tighten the type to match).
- **Engineer audit task:** grep `fhir4ds/cql/` for `.source_path` references and
  confirm none assume non-None when `provenance != "local_file"`. Specifically
  check `loader/fhir_loader.py:560` (verified 2026-07-03 — only reads `codes`).

### 4.8 Modify `pyproject.toml` — add `[fhir4ds,terminology]` extra

```toml
[project.optional-dependencies]
# ... existing extras unchanged ...
terminology = [
    "httpx>=0.24",
    # medterm4ds is intentionally NOT declared here — it's a sibling repo.
    # Users install both manually. The factory raises ImportError with a
    # clear install hint if medterm4ds is missing in in_process mode.
]
```

### 4.9 Out-of-Phase-1 (deferred to Phase 1.5)

The following are explicitly **not** in Phase 1:
- Removing `terminologyEndpoint` from `_UNSUPPORTED_TOP_LEVEL` in `fhir4ds/cql/fhir_server/parameters.py`.
- Adding a `terminology_endpoint=` parameter to `evaluate_measure(...)` in `fhir4ds/cql/__init__.py`.
- Per-call expand result caching.

---

## 5. Test Strategy

### 5.1 Unit tests — `fhir4ds/cql/tests/unit/terminology/`

- **`test_endpoint_protocol.py`** — A trivial stub class implementing the four methods satisfies `isinstance(x, TerminologyEndpoint)` via Protocol (structural typing).
- **`test_http_adapter.py`** — Mock `httpx.Client`; verify request URL/path/params, response parsing for empty/normal/large expansions, system normalization (incl. SNOMED module URL → base URL — INV-5 regression).
- **`test_in_process_adapter.py`** — Mock medterm4ds service functions; verify `CodeRef` mapping and `index_version` propagation.
- **`test_factory.py`** — Env-var matrix:
  - `FHIR4DS_TERMINOLOGY_MODE=disabled` → returns `None`.
  - `FHIR4DS_TERMINOLOGY_MODE=http&URL=...` → returns `HTTPTerminologyEndpoint`.
  - `FHIR4DS_TERMINOLOGY_MODE=http` without URL → `ValueError`.
  - `FHIR4DS_TERMINOLOGY_MODE=in_process` without `medterm4ds` installed → `ImportError` with the install hint.
  - Mode unset → `None` (zero-dep default).
- **`test_import_isolation.py`** (NEW — addresses INV-3 from audit):
  - `import fhir4ds.cql.terminology.in_process_adapter` must NOT leave `httpx` in `sys.modules`.
  - `import fhir4ds.cql.terminology.http_adapter` must NOT leave `medterm4ds` in `sys.modules`.
- **`test_env_laziness.py`** (NEW — addresses INV-4 from audit):
  - Spy on `os.getenv` and assert that after `import fhir4ds.cql.terminology.factory`, no `FHIR4DS_TERMINOLOGY_*` lookup has occurred.
  - Calling `get_terminology_endpoint()` does invoke `os.getenv`.

### 5.2 Unit tests — `fhir4ds/cql/tests/unit/test_resolver_fallback.py`

- `terminology_endpoint=None` → `resolve_valueset(unknown_url)` returns `None` exactly as today (regression).
- Mock endpoint returns `[CodeRef(...)]` → `resolve_valueset(url)` returns `ResolvedValueSet` with `provenance="terminology_endpoint"` and codes populated.
- Mock endpoint raises `httpx.ConnectError` → `resolve_valueset` returns `None`, emits WARNING (use `caplog`).
- Local match always wins: pre-load a local ValueSet, ensure the endpoint is never called.
- `ResolvedValueSet.source_path` is `None` for endpoint-resolved values; engineer verifies no downstream code dereferences it without checking.

### 5.3 Integration tests — `fhir4ds/cql/tests/integration/test_medterm4ds_endpoint.py`

- Auto-skipped if `MEDTERM4DS_TEST_URL` env var is unset.
- When set:
  - `expand("http://snomed.info/sct?fhir_vs=isa/73211009")` returns a non-empty list including code `73211009` (Diabetes).
  - `search_text("diabetes", "condition")` returns ranked results with `match_grade` populated.

### 5.4 Regression — conformance baseline

`python3 conformance/scripts/run_all.py` MUST remain at the current baseline.
Per `conformance/reports/dqm_report.json` (verified 2026-07-03):
- CQL DQM suite: 47/47 measures passing, 100% accuracy.
- Total conformance pass count target: **2822/2822** (per `USER_DIRECTIVES.md`).
- Phase 1 is purely additive (`terminology_endpoint=None` is the default), so regression risk is essentially zero.

---

## 6. Validation Commands

The implementation engineer MUST run, in order:

1. `python3 -m pytest fhir4ds/cql/tests/unit/terminology/ -v`
2. `python3 -m pytest fhir4ds/cql/tests/unit/test_resolver_fallback.py -v`
3. `python3 -m pytest fhir4ds/cql/tests/unit/test_resolver.py -v` (existing resolver regression)
4. Zero-dep default check:
   ```bash
   python3 -c "import fhir4ds; import fhir4ds.cql.terminology; print('OK')"
   ```
   Must succeed with NO `httpx`, NO `medterm4ds` installed.
5. `python3 conformance/scripts/run_all.py 2>&1 | tail -50`
   Expected: 2822/2822 (no regression).
6. (If live medterm4ds available)
   `MEDTERM4DS_TEST_URL=http://127.0.0.1:8001 \
    python3 -m pytest fhir4ds/cql/tests/integration/test_medterm4ds_endpoint.py -v`

---

## 7. Deferred / Open Questions (Phase 1+ follow-ups)

These are intentionally **out of Phase 1 scope** and are tracked for downstream FDDs:

1. **Plumb `terminology_endpoint` through `evaluate_measure(...)` and the FHIR `$cql` facade.**
   Phase 1 wires the abstraction and `DependencyResolver` only. Public top-level
   plumbing requires a new parameter on `evaluate_measure` and removing
   `terminologyEndpoint` from `_UNSUPPORTED_TOP_LEVEL` in
   `fhir4ds/cql/fhir_server/parameters.py`. Recommend a Phase 1.5 task before
   Phase 2.
2. **Result caching for `expand()`.** Repeated calls for the same URL within a
   single library translation should hit an in-memory cache. Defer to a Phase
   1.5 micro-optimization (Phase 3's closure-table work will subsume this).
3. **Async batch `$expand`.** medterm4ds does not yet expose a batch expand.
   Phase 1's `search_batch` covers discovery; batch expand is a Phase 3 need.
4. **Integration-point drift confirmed vs. original plan (2026-07-02):**
   - Plan cited `duckdb/macros/list.py:528` for the `descendents` identity bug.
     **Current location: `duckdb/macros/list.py:577`** (drift of +49 lines from
     the spec-compliance campaign).
   - Plan cited `_operators.py:5102` for `_codes_equivalent`.
     **Current location: `_operators.py:5499`** (drift of +397 lines).
   - These drifts are **Phase 3 concerns**; Phase 1 does not touch either file.
     Recorded for the Phase 3 FDD.

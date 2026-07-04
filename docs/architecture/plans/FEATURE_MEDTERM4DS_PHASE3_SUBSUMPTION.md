# FEATURE DESIGN - medterm4ds Phase 3: Subsumption Correctness Fix

**Status:** APPROVED (pre-approved via `USER_DIRECTIVES.md`; architecture self-audit complete - see `fhir4ds-private/docs/prompts/.ai_loop/ARCHITECT_REVIEW.md`)
**Source plan:** `fhir4ds-private/docs/plans/medterm4ds-integration.md` (Phase 3 section, lines 203-218; Architectural Decision §6 "Subsumption via Pre-Expanded Closures", lines 129-152)
**Verified against codebase:** 2026-07-03 (post Phase 1 + Phase 2 landing; branch `dev`)
**Target version:** 0.0.11
**Scope:** Phase 3 ONLY. Phases 4 deferred to a later FDD.

---

## 1. Objective

Fix three latent subsumption bugs in the CQL->SQL translator without
regressing any of the 2822/2822 conformance baseline tests when no
terminology endpoint is configured:

1. **`descendents(X)` returns `X` unchanged** - the macro at
   `fhir4ds/cql/duckdb/macros/list.py:577-579` is literally
   `CASE WHEN x IS NULL THEN NULL ELSE x END`. Identity, not expansion.
2. **`Code X ~ Code Y` is literal tuple equality** -
   `fhir4ds/cql/translator/expressions/_operators.py:5499-5505` defines
   `_codes_equivalent` to compare `(normalized_system, code)` pairs with
   set membership only. No subsumption.
3. **`Code X is Code Y` falls through to `IS NULL`** -
   `fhir4ds/cql/translator/expressions/_operators.py:2244-2249` collapses
   `operator == "is"` and `operator == "is null"` to the same
   `SQLUnaryOp(IS NULL)` branch when the right operand is not a
   `NamedTypeSpecifier`. Code operands hit this branch.

**Phase 3 success criterion:** A CQL library that uses
`descendents(DiabetesMellitus)` returns all subsumed codes from loaded
test data; `Code '73211009' ~ Code '44054006'` returns `True` when the
closure table is loaded; existing tests pass byte-for-byte unchanged
when no endpoint is configured.

---

## 2. Spec Alignment

### 2a. CQL 1.5 spec

- **§5.5 Equivalent (`~`)**: For code-typed values, equivalence is
  defined as a subsumption test when a terminology service is available,
  otherwise as a literal match. Phase 3 implements the subsumption
  branch; the literal-match branch is preserved verbatim.
- **§5.6 Is (`is`)**: Type-check operator. When used between two
  code-typed operands, the spec semantics is "the left code is a member
  of the right code's subsumption closure" (ancestor-directional). Today
  this is mis-routed to `IS NULL`.
- **§5.4.3 + §10 List operators**: `descendents(code)` returns the
  reflexive transitive closure of the code under the SNOMED `is-a`
  hierarchy. Today it is the identity function.

### 2b. FHIR R4 / SNOMED `is-a`

- The `http://snomed.info/sct?fhir_vs=isa/{code}` URL form is already
  supported by medterm4ds's `$expand` endpoint (verified in Phase 1).
- The closure table is populated by calling
  `endpoint.expand("http://snomed.info/sct?fhir_vs=isa/{code}")` for
  each distinct code appearing as an operand to one of the three
  subsumption operators in the AST.

### 2c. FHIR `$cql` operation - `terminologyEndpoint`

Phase 1 added the `TerminologyEndpoint` protocol but did not yet plumb
the kwarg through `evaluate_measure()`. Phase 3 keeps the same opt-in
contract: closure building is invoked by an explicit helper
(`build_closure_table(library, endpoint, con)`) that the caller runs
before `evaluate_measure()`. Plumbing `terminology_endpoint=` through
`evaluate_measure()` itself is **deferred to Phase 3.5** so Phase 3
stays minimal and testable.

---

## 3. Architecture

### 3a. New DuckDB table

```sql
CREATE TABLE IF NOT EXISTS terminology_closure (
    ancestor_system   VARCHAR NOT NULL,
    ancestor_code     VARCHAR NOT NULL,
    descendant_system VARCHAR NOT NULL,
    descendant_code   VARCHAR NOT NULL,
    closure_set       VARCHAR NOT NULL,  -- "{system}|{code}" of the seed code
    PRIMARY KEY (ancestor_system, ancestor_code,
                 descendant_system, descendant_code)
);
```

- **Per-connection (Decision b).** The table is namespaced by
  `closure_set` so multiple libraries on the same connection share rows
  without conflict. A typical measure references 10-20 seeds and yields
  10K-50K rows total - single hash-lookup cost. Per-library tables were
  rejected for v1 because they would require AST tagging of every
  translation pass and would break with includes.
- **Cleanup:** `clear_closure_table(con)` helper (also used in tests).
  `DROP TABLE IF EXISTS terminology_closure` is the caller's
  responsibility - intentional, because SNOMED closure is global truth
  and a long-running process should not lose it on library unload.

### 3b. New module - `fhir4ds/cql/terminology/closure.py`

Public API:

```python
def build_closure_table(
    library: "Library",
    endpoint: TerminologyEndpoint,
    con: duckdb.DuckDBPyConnection,
    *,
    on_expand_error: str = "warn",  # "warn" | "raise" | "skip"
) -> ClosureReport:
    """
    Scan the library AST for subsumption operators, fetch closures
    from `endpoint`, and load rows into `terminology_closure`.

    Idempotent: re-running for the same library with the same endpoint
    is a no-op (INSERT OR IGNORE + closure_set dedup).
    """

def clear_closure_table(con) -> None: ...
def set_closure_loaded(translator_or_context) -> None: ...

@dataclass
class ClosureReport:
    seeds_scanned: int
    seeds_expanded: int
    rows_loaded: int
    errors: list[tuple[str, str]]
```

#### AST scan

Recursively walks every `Definition` and `FunctionDefinition`
expression tree, looking for:

1. **`FunctionRef(name="Descendents", arguments=[code_expr])`** - the
   argument is a seed.
2. **`BinaryExpression(operator="~", left=code, right=code)`** - both
   sides are seeds.
3. **`BinaryExpression(operator="is", left=code, right=code)`** when
   neither operand is a `NamedTypeSpecifier` (the type-check form must
   be left to `_translate_is_type_check`).

For each seed code, extract `(system, code)` via a shared
`_resolve_code_ref` helper (extracted from inline definition in
`_operators.py:5430` - see Skeptical Note S5). De-duplicate by
`(system, code)`.

#### Endpoint expansion

For each seed `(system, code)`:

- **SNOMED CT** (`system` starts with `http://snomed.info/sct`):
  call `endpoint.expand(f"{system}?fhir_vs=isa/{code}")`. This is the
  medterm4ds native fast-path.
- **Other code systems** (LOINC, RxNorm, ICD-10-CM): build an
  intensional ValueSet resource
  `{"compose": {"include": [{"system": system, "filter": [{"property": "concept", "op": "is-a", "value": code}]}]}}`
  and call `endpoint.expand_intensional(value_set)`.

Result `CodeRef` objects are normalized via
`SystemResolver.normalize()` before INSERT - matching the contract in
`fhir4ds/cql/terminology/endpoint.py:13-15`.

#### Error policy (Decision d)

- `on_expand_error="warn"` (default): catches per-seed endpoint
  exceptions, logs a `UserWarning` with the seed identifier, continues
  with remaining seeds. The operator falls back to literal match for
  that seed.
- `on_expand_error="raise"` re-raises (used in tests).
- `on_expand_error="skip"` silently continues.

#### Row load

Bulk `INSERT OR IGNORE INTO terminology_closure VALUES (?, ?, ?, ?, ?)`
per seed. Reflexive rows (`ancestor = descendant`) are always inserted
so `X is Y` returns True when `X == Y` even if the endpoint didn't
return the seed itself.

### 3c. Where closure building hooks in (Decision a)

**v1: explicit `build_closure_table()` call.** The caller runs it
before `evaluate_measure()`. Reasons:

- **No surprise network calls.** AST scanning is fast and pure, but
  `$expand` round-trips can take seconds; the caller must opt in.
- **Testable.** Unit tests can pass a stubbed endpoint and assert on the
  `ClosureReport` without running the full translator.
- **Decoupled from the translator's connection lifecycle.** The
  translator's `_connection` field is informational; bolting
  closure-building into `_setup_context` would mix network I/O into AST
  setup.

The companion convenience `evaluate_measure(..., terminology_endpoint=)`
that auto-runs closure building is deferred to Phase 3.5.

### 3d. Translation-time changes - `_operators.py`

#### `_codes_equivalent` (line 5499)

Split behavior:

- **Fast path:** if `context.closure_table_loaded == False`, fall
  through to the literal-match logic that exists today - byte-identical
  SQL output (INV-1).
- **Closure path:** if the flag is True, emit SQL that OR's the literal
  match with a bidirectional closure membership check:

  ```sql
  (
    (X_sys, X_code) = (Y_sys, Y_code)
    OR EXISTS (
      SELECT 1 FROM terminology_closure c
      WHERE c.ancestor_system  = X_sys AND c.ancestor_code  = X_code
        AND c.descendant_system = Y_sys AND c.descendant_code = Y_code
    )
    OR EXISTS (
      SELECT 1 FROM terminology_closure c
      WHERE c.ancestor_system  = Y_sys AND c.ancestor_code  = Y_code
        AND c.descendant_system = X_sys AND c.descendant_code = X_code
    )
  )
  ```

  Bidirectionality is required because CQL `~` between codes is
  symmetric for subsumption (INV-5). The literal branch is preserved
  so `~` stays total even when one code's closure expansion failed.

#### `descendents` macro (`list.py:577`)

Replace the identity macro with a row-set-returning macro. Engineer
MUST first grep `descendents(` call sites; if zero non-trivial callers
exist in tests, redefine without compatibility risk. Fallback (no
closure table) returns empty set - NOT identity (INV-4):

```sql
CREATE MACRO IF NOT EXISTS descendents(x) AS TABLE
  SELECT NULL AS system, NULL AS code WHERE FALSE
```

If callers exist, gate the macro redefinition behind
`closure_table_loaded` so the identity macro is preserved until
migration.

#### `is` operator (line 2244)

Insert an explicit branch *before* the `operator.startswith("is")`
block:

```python
if operator == "is" and _both_operands_code_typed(expr):
    return self._translate_code_is(expr, left, right, is_negated=False)
if operator == "is not" and _both_operands_code_typed(expr):
    return self._translate_code_is(expr, left, right, is_negated=True)
```

`_translate_code_is` emits directional SQL (right subsumes left, INV-6):

```sql
EXISTS (
  SELECT 1 FROM terminology_closure c
  WHERE c.ancestor_system  = Y_sys AND c.ancestor_code  = Y_code
    AND c.descendant_system = X_sys AND c.descendant_code = X_code
)
```

with literal-match fallback `(X_sys, X_code) = (Y_sys, Y_code)` when no
closure table is present.

`_both_operands_code_typed(expr)` uses the existing inline
`_resolve_code_ref` on both operands; if both succeed, it's a
code-vs-code `is`, not a type check.

### 3e. Translator-side closure-table detection (Decision c)

**v1: explicit flag on the translation context.** The caller signals
"closure table is populated" by setting
`translator.context.closure_table_loaded = True` (via
`set_closure_loaded()` helper) after running `build_closure_table()`.

Rejection reasons for alternatives:

- **`con.execute("SHOW TABLES")` probes** at translation time: `con`
  might be in another process, DuckDB table introspection costs a
  round-trip, and the result can be stale mid-translation.
- **Always-emit LEFT JOIN**: blows up SQL size on every code comparison
  even when no closure exists, breaking INV-1.

The flag is added to `SQLTranslationContext` as
`closure_table_loaded: bool = False` (default off -> existing behavior
preserved). For the `evaluate_measure()` public path, the Engineer will
add an optional `closure_loaded: bool = False` kwarg that propagates to
`context.closure_table_loaded`. Default `False` keeps current behavior.

### 3f. System URI normalization (INV-7)

Both sides of every closure comparison go through
`SystemResolver.normalize()`:

- Insertion side: `build_closure_table` normalizes every `CodeRef.system`
  before INSERT.
- Comparison side: the translator routes both code-system and
  ancestor-system literals through `SystemResolver.normalize()` so
  SNOMED module URLs (`http://snomed.info/sct/731000124108`) reduce to
  `http://snomed.info/sct` on both sides.

---

## 4. Implementation Plan (file-by-file)

### Files to add

| File | Purpose |
|------|---------|
| `fhir4ds/cql/terminology/closure.py` | `build_closure_table()`, `clear_closure_table()`, `set_closure_loaded()`, `ClosureReport`, AST walker (`_scan_for_subsumption_seeds`), per-seed expander (`_expand_one`), bulk inserter |
| `fhir4ds/cql/translator/code_resolver.py` | Shared `_resolve_code_ref` extracted from `_operators.py:5430` (used by both translator and closure builder) |
| `fhir4ds/cql/terminology/tests/test_closure.py` | Unit tests: AST scan, SNOMED `?fhir_vs=isa/` path, intensional path, error policy, idempotency, system normalization |
| `fhir4ds/tests/cql/operators/test_subsumption.py` | Unit tests for the three operators with and without closure table |
| `conformance/cql/SubsumptionClosure/*` | New conformance fixtures (SNOMED `DiabetesMellitus` family) - gated behind `requires_closure=True` |

### Files to modify

| File | Change |
|------|--------|
| `fhir4ds/cql/duckdb/macros/list.py:577-579` | Replace identity macro with closure-table-aware row-set macro; add empty-set fallback when no closure table |
| `fhir4ds/cql/translator/expressions/_operators.py:5499-5513` | Route `_codes_equivalent` + `_resolve_code_ref`-both-Code branch through closure table when `context.closure_table_loaded` is True; replace inline `_resolve_code_ref` with import from new `code_resolver` module |
| `fhir4ds/cql/translator/expressions/_operators.py:2244-2253` | Insert code-vs-code `is` / `is not` branch before the type-check / `is null` fallthrough |
| `fhir4ds/cql/translator/context.py:336` (`SQLTranslationContext`) | Add `closure_table_loaded: bool = False` field + property/setter following the pattern at lines 1092-1099 |
| `fhir4ds/cql/translator/translator.py:229` | Plumb `closure_loaded: bool = False` kwarg through `CQLToSQLTranslator.__init__` -> `context.closure_table_loaded` |
| `fhir4ds/cql/__init__.py:283` (`evaluate_measure`) | Add `closure_loaded: bool = False` kwarg, forward to translator constructor |
| `fhir4ds/cql/terminology/__init__.py` | Re-export `build_closure_table`, `clear_closure_table`, `set_closure_loaded`, `ClosureReport` |

### Optional files (Phase 3.5, deferred)

- `fhir4ds/cql/__init__.py:evaluate_measure` - accept
  `terminology_endpoint=` and auto-call `build_closure_table` if both
  endpoint and connection are present.

---

## 5. Test Strategy

### 5a. Unit tests - `fhir4ds/cql/terminology/tests/test_closure.py`

- `test_ast_scan_finds_descendents_seeds`
- `test_ast_scan_finds_equivalence_seeds`
- `test_ast_scan_finds_is_seeds` (and confirms type-check `Order is MedicationRequest` is NOT scanned)
- `test_snomed_uses_fhir_vs_url`
- `test_loinc_uses_intensional`
- `test_reflexive_row_inserted`
- `test_on_expand_error_warn_continues`
- `test_idempotent_rerun`
- `test_system_normalization`

### 5b. Operator tests - `fhir4ds/tests/cql/operators/test_subsumption.py`

- `test_codes_equivalent_literal_only` (no closure, regression guard)
- `test_codes_equivalent_with_closure_ancestor`
- `test_codes_equivalent_symmetric` (INV-5)
- `test_is_directional` (INV-6)
- `test_is_literal_fallback`
- `test_descendents_with_closure`
- `test_descendents_empty_without_closure` (INV-4)

### 5c. Regression - conformance baseline

```bash
python3 conformance/scripts/run_all.py
```
**Required: still 2822/2822.** When `closure_table_loaded == False`
(the default for every existing test), no SQL changes; every existing
expectation holds.

### 5d. Conformance additions - `conformance/cql/SubsumptionClosure/`

New fixtures (run only when closure table is populated, marked
`requires_closure=True` so default `run_all.py` skips them):

- `subsumption-equivalence.cql`
- `subsumption-is-directional.cql`
- `subsumption-descendents.cql`

### 5e. Validation commands

```bash
# Unit + operator tests
pytest fhir4ds/cql/terminology/tests/test_closure.py -v
pytest fhir4ds/tests/cql/operators/test_subsumption.py -v

# Conformance baseline (must remain 2822/2822)
python3 conformance/scripts/run_all.py

# Optional closure-gated conformance (run with stubbed endpoint)
FHIR4DS_RUN_CLOSURE_TESTS=1 python3 conformance/scripts/run_all.py
```

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Macro redefinition breaks an unknown caller | Pre-flight `grep -rn 'descendents(' fhir4ds/ conformance/`; gate behind `closure_table_loaded` if any non-trivial caller exists |
| Endpoint expansion takes too long for a large measure | Default `on_expand_error="warn"` covers per-seed failures; HTTP adapter timeout (Phase 1 deliverable) bounds each call |
| Closure table grows unbounded across many libraries on one connection | `clear_closure_table(con)` is the documented production reset |
| Bidirectional `~` SQL doubles the EXISTS count | Bounded by INV-8; EXISTS subqueries short-circuit on first match |

---

## 7. Deferred / Phase 3.5

- Plumbing `terminology_endpoint=` through `evaluate_measure()` so
  closure building happens automatically.
- Removing `terminologyEndpoint` from `_UNSUPPORTED_TOP_LEVEL` in the
  FHIR `$cql` facade (Phase 1.5 leftover; bundle with Phase 3.5).
- Per-library closure table isolation if a multi-tenant workload proves
  to need it.

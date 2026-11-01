# Architecture Self-Audit — WASM C++ Parity Feature

Auditor: Feature Designer (self-audit per ROLE_FEATURE_DESIGNER step 3)
Draft audited: FEATURE_PLAN_DRAFT.md v1
Standards: ROLE_ARCHITECT.md (layering, boundaries, spec alignment, validation, regression)

---

## Invariants (falsifiable)

**INV-1 (Authority preservation):** After the feature, on a desktop native-loaded
connection, every one of the 10 ported functions that is in `_PYTHON_PREFERRED_CPP_CONFLICTS`
remains Python-backed; none of the 10 ported functions is added to that list.
FALSIFIABLE: `grep _PYTHON_PREFERRED_CPP_CONFLICTS fhir4ds/cql/duckdb/extension.py`
shows no additions; forced-Python parity tests still pass.

**INV-2 (Registration skip correctness):** With cpp_loaded=True, `_SafeConnection`
skips Python `create_function` for exactly the C++-registered names; no
double-registration CatalogException; no silent Python shadow of a C++ function.
FALSIFIABLE: native-loaded connection `duckdb_functions()` shows the C++
implementations (function_type='scalar' from extension) for the 10 names; no
duplicate Python entries.

**INV-3 (No-Python completeness):** On a no-Python connection (extension + macros
only), all 10 functions resolve and execute; the cql-clinic cqlDivide repro
(previously Catalog Error) returns a result.
FALSIFIABLE: no-Python parity test file executes each function directly.

**INV-4 (Parity equivalence):** For every ported function and every test case,
forced-Python, native-loaded, and no-Python C++ outputs are identical (incl.
NULL vs None, decimal text, list shapes, transport markers).
FALSIFIABLE: 3-path parity test suite, per-function.

**INV-5 (WASM binary parity):** `make wasm_eh` from both extension dirs produces
binaries deployed to BOTH web/wasm-demo/public/extensions and
web/cql-clinic/public/extensions; md5(build) == md5(repo deploy) for each target.
FALSIFIABLE: md5sum comparison post-deploy.

**INV-6 (Dead code actually dead):** ConvertQuantity/cqlDateTimeSubtract/cqlNormalizeTZ/
PascalCase WeeksBetween+MillisecondsBetween have zero remaining references after
deletion (grep clean; translator emits unchanged; master gate 2832/2832).
FALSIFIABLE: `grep -rn "ConvertQuantity\|cqlDateTimeSubtract\|cqlNormalizeTZ" fhir4ds/`
returns only historical docs/AGENTS or nothing.

**INV-7 (No macro fallback leakage):** cql-macros.ts unchanged (no entries for
the 13); no new `__EMSCRIPTEN__` branches in C++ sources.
FALSIFICable: `grep -rn "__EMSCRIPTEN__" extensions/cql/src` shows no new sites;
`git diff web/wasm-demo/src/lib/cql-macros.ts` empty.

**INV-8 (Gate non-regression):** Master conformance 2832/2832 and DQM 47/47 hold
on the final tree with both rebuilt native binaries deployed.
FALSIFIABLE: run_all.py fresh run.

## Skeptical Notes (design-level)

S-1. **cqlDivide exact-decimal in C++ is the highest-risk port.** Python uses
`decimal.Decimal` division with ROUND_HALF_UP at scale 8. The fhirpath prior art
(`exactDecimalRatioText`) implements 28-sig-digit ROUND_HALF_EVEN — a DIFFERENT
rounding mode and precision target. The engineer must implement scale-8
ROUND_HALF_UP text division, not copy the fhirpath helper blindly.
→ Plan must state: rounding mode ROUND_HALF_UP, scale 8, extent checks matching
`_cql_divide`'s guards (NULL on non-numeric, zero-divisor, extent overflow).

S-2. **CQLMessage is currently macro-first (SQL macro takes precedence on desktop).**
Porting to C++ changes the desktop native path from macro→C++ (macro registration
happens on the real con; C++ functions are registered... wait — macros and
functions live in different namespaces in DuckDB; a TEMP MACRO `CQLMessage`
shadows the extension function by name). VERIFY at impl: on native-loaded path,
does the SQL macro still shadow the C++ function? If the macro always wins on
desktop, C++ port only benefits the no-Python path — which is the goal (browser).
But the no-Python path must then also register the macro (macros register via
register_all_macros on any connection; no-Python connections get macros too).
Actually no-Python C++ connections DO get SQL macros (extension.py registers
macros on all paths). So CQLMessage may already work no-Python via macro. The
C++ port is then optional for CQLMessage — keep it for uniformity, but the
critical parity target is: macro path (desktop) == C++ path (browser). Both must
implement Error-severity error() semantics identically. Existing tests
(test_message_parity.py, 13/13) cover desktop paths; add no-Python coverage.
RECOMMENDATION: port CQLMessage to C++ anyway (directive lists it), ensure the
macro does not shadow it in the browser, and add no-Python tests.

S-3. **fhirpath_in_valueset C++ shares g_valueset_cache — but the Python version
is a FACTORY closure over a per-loader cache.** In C++, the cache is a global
populated by ValuesetCacheAdd. Parity requires: cache populated identically
(already the case for in_valueset), String-overload ambiguity scan, notDoneValueSet.
The InValuesetFunc precedent is parity-proven — the new function is essentially
an alias/wrapper with path extraction. Low residual risk, but the path-extraction
side (resource,path) is the new surface: Python traverses `path` via
fhirpath_text-style extraction; C++ InValuesetFunc already does this (3-arg form).
Verify the 3-arg form matches Python fhirpath_in_valueset(resource, path, url)
exactly (arg order/semantics).

S-4. **cqlChildren/cqlDescendants transport markers are load-bearing for the
translator** (CQL-05 doctrine: `__fhir4ds_cql_type` markers; Children/Descendants
must recursively wrap nested Date/DateTime/Time/Long). The C++ implementation
must produce byte-identical JSON marker shapes. This is the second-highest-risk
port. Mitigation: port `_encode_structural_item` semantics 1:1; test marker
shapes explicitly (Date/Time/DateTime/Long/nested list/tuple).

S-5. **Deletion of ConvertQuantity: test_conversion_check_parity.py:35** uses the
name in a define — if the CQL `convert ... to` syntax routes to quantityConvert,
the registration is truly dead; if the test calls the UDF name directly in SQL
inside the define, deleting the reg breaks it. Engineer must verify routing
BEFORE deleting (plan §2.2 already notes this). If broken, update test to use
quantityConvert.

S-6. **Casing reconciliation scope:** Only WeeksBetween/MillisecondsBetween
collide. DaysBetween/HoursBetween/etc. (PascalCase Python-only) must NOT be
deleted — they are the only registration for those names (no C++ counterpart).
The plan already says this; keep it explicit in the handoff.

S-7. **WASM rebuild requires BOTH extensions** (fhirpath binary embeds nothing
new, but the cql wasm must link against the same duckdb-wasm version; and the
directive says rebuild both). Also: fhirpath extension is untouched by this
feature — rebuilding it is a no-op risk check only. Confirm directive intent:
rebuild both per directive; fhirpath rebuild validates env, not new code.

S-8. **_SafeConnection skip semantics:** The 10 new C++ registrations will cause
Python supplement registrations to be SKIPPED on native-loaded desktop. This is
the desired end state, but it means desktop native behavior CHANGES from
Python-implemented to C++-implemented for these 10. Parity tests (INV-4) are the
only guard. Any of the 10 with subtle Python-only behaviors (e.g. warnings,
logging) will change observable behavior. Audit each Python UDF for side effects
behind return values (logging only — acceptable).

## Verdict

Draft is architecturally sound with 8 verifiable invariants. Conditions before
implementation:
1. S-1: plan must specify ROUND_HALF_UP scale-8 (not fhirpath's HALF_EVEN).
2. S-2: CQLMessage macro/C++ interplay verified at impl; no-Python tests added.
3. S-4: cqlChildren marker parity tests are mandatory.
4. S-5: ConvertQuantity routing verified before deletion.
5. S-8: per-function side-effect audit (logging-only acceptable).

Proceed to refinement (v2) incorporating these notes.

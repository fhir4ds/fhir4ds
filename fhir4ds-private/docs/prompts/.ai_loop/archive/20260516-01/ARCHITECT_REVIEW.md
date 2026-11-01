# Architecture Self-Audit: WASM CQL Complete Runtime Parity

## Invariants

1. **No Python DuckDB UDFs in browser execution**
   Any SQL emitted by supported CQL translation must execute in DuckDB-WASM with
   only C++ extensions, SQL macros, and DuckDB builtins.

2. **Translator support boundary is explicit**
   The campaign covers CQL accepted by the current translator. Unsupported CQL
   must fail at translation time with clear errors, not at WASM runtime through
   missing functions.

3. **Inventory is generated, not hand-maintained**
   Function coverage must be derived from source/catalog output and translator
   emission, not from a manually curated list that can drift.

4. **Python remains oracle, not fallback, for parity closure**
   Python UDFs may be used in tests to define current expected behavior, but not
   to satisfy the no-Python runtime gate.

5. **Shadowing cannot hide browser failures**
   `_PYTHON_PREFERRED_CPP_CONFLICTS` must shrink or be proven irrelevant for
   supported browser CQL. Native conformance cannot be accepted as evidence of
   WASM correctness when Python macros shadow C++.

6. **Spec semantics override implementation accidents**
   When Python and C++ disagree, the fix must cite CQL/FHIRPath semantics and
   update both paths if Python is wrong.

7. **Release artifacts are first-class outputs**
   Extension changes are incomplete until native binaries, WASM side modules,
   wheel, Vite build, website static assets, and browser tests are refreshed.

8. **No clinical hardcoding is introduced**
   Valueset, profile, CMS, QICore, and measure behavior must remain data-driven
   and test-fixture-specific knowledge must stay out of generic runtime logic.

## Findings

### Finding 1: Draft Must Avoid Exact-Name False Positives

Severity: medium.

The initial inventory is useful but exact-name comparison can overstate gaps
when SQL macros or C++ aliases intentionally expose different names from Python
direct UDFs. The final gate must classify by translator-emitted name and
runtime catalog availability, not by Python UDF name alone.

Resolution in refined plan: inventory columns distinguish Python UDF, C++ UDF,
SQL macro, DuckDB builtin, emitted name, and required status.

### Finding 2: Direct Native Tests Are Necessary But Not Sufficient

Severity: high.

Native direct-extension tests catch Python fallback leakage but cannot prove
DuckDB-WASM dynamic linking, asset copying, Pyodide translation, or browser
macro registration.

Resolution in refined plan: browser/WASM translate-and-execute gate is required
in addition to direct native no-Python tests.

### Finding 3: Full CQL Claim Needs A Support Boundary

Severity: high.

"Any CQL" is ambiguous because the translator does not support every possible
CQL language feature. Without a boundary, acceptance could be impossible or
could silently exclude features.

Resolution in refined plan: objective states "any CQL accepted by the current
fhir4ds Python translator as supported behavior"; unsupported features must fail
clearly at translation time.

### Finding 4: Shadowed Functions Are The Highest-Risk Semantic Gap

Severity: high.

The existence of C++ functions is not parity when native registration still
shadows them with Python to preserve conformance. These names must be treated
as unproven until direct C++ parity tests cover their edge cases.

Resolution in refined plan: dedicated phase to remove or justify every shadowed
name, with translator-required names prohibited from remaining shadowed at
final acceptance.

### Finding 5: Validation Must Include Full Regression Gates

Severity: medium.

Focused parity tests alone can miss regressions in FHIRPath, ViewDefinition,
DQM, package import, or browser artifact paths.

Resolution in refined plan: acceptance requires full `pytest fhir4ds`,
conformance `run_all.py`, C++ SQL suites, Playwright, and release artifact gates
when relevant.

## Verdict

The plan is architecturally sound after refinement. The critical improvement is
that the campaign starts with a generated emitted-function inventory and treats
Python/C++ semantic shadowing as unresolved work, not as an implementation
detail.


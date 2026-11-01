# QA Handoff - FP-12 EXPLORER

## Scope

Fresh FP-12 EXPLORER pass for FHIRPath N1 sections 5.8 and 5.9:
`children()`, `descendants()`, `trace(name, [projection])`, `now()`,
`timeOfDay()`, and `today()`.

Normative anchors checked from https://hl7.org/fhirpath/N1/:
- 5.8.1: `children()` returns all immediate child nodes; order is undefined.
- 5.8.2: `descendants()` returns all descendant nodes, excluding the input nodes, shorthand for `repeat(children())`; order is undefined.
- 5.9.1: `trace(name, projection)` logs the projection result while returning the original input unchanged.
- 5.9.2: current-time functions use an implementation-defined timestamp, but `now()`, `timeOfDay()`, and `today()` should be stable no matter how many times they are evaluated within one expression.

## Probes Run

- Created scratch probe `.temp/qa/fp12_explorer_probe.py`.
- Compared native/C++ DuckDB registration and forced Python fallback on tree navigation, null children, nested contained resources, Unicode string descendants, trace projection return behavior, and current-time output shapes.
- Ran existing focused parity test:
  `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py -q`

## Finding

QA-001 HIGH: native C++ `now()`, `today()`, and `timeOfDay()` read `time(nullptr)` independently on each invocation. A long single expression can cross a second boundary and make `now() = now()` false. Forced Python fallback uses per-expression `Constants.systemtime` and returns true.

Concrete reproducer used during QA:
`now() = iif(descendants().count() > 0 and ... repeated 8 times ..., now(), now())`
against a Patient resource with 40k-80k extension children. Native returned `False` before remediation when the expression crossed a second boundary; fallback returned `True`.

## Handoff

Remediation should cache the native current timestamp for the duration of one
`Evaluator::evaluate()` call and rebuild/copy the bundled
`fhirpath.duckdb_extension`. Add a native/fallback parity regression for this
case.

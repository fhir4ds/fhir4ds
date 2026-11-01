# Engineer Handoff — CQL-05 Structural Type Operators (HISTORIAN, iteration 1)

## QA-101 (HIGH) — RESOLVED. As-cast query-source aliases bound to retrieve rows
Spec: CQL 1.5 §Query (source alias binds each element) + §As (null on mismatch) + §Is
(`null is T` false). Symptom: `Count([Observation] O return O.value as FHIR.Quantity Q where
Q is FHIR.Quantity)` → 0 (expected 1); `Q is not null` → 2 (expected 1); even
`'x' as String X where X is String` → 0.

Root cause (3 layers):
1. `fhir4ds/cql/translator/expressions/_query.py` — when a nested-query source's SQL contained a
   retrieve placeholder, the CTE-flatten branch replaced the whole source with
   `SELECT * FROM <cte> AS <alias>`, discarding the inner query's projection. Fix: when the inner
   select's projection is a computed VALUE (not `*`/`.resource`), preserve it as
   `SELECT <value> AS <alias> FROM <inner FROM>` and register the alias as an element-value alias
   (`add_alias(table_alias=alias)` + `_alias_source_asts[alias] = <Query node>`). A second
   defensive branch for SQLSubquery-shaped nested sources mirrors this in the single-source path.
2. `_alias_is_element_value()` now returns True for Query sources (alias iterates values, no
   `.resource` qualification); `_core.py::_translate_identifier` returns the bare column for
   Query-source aliases (same as list literals).
3. Static is-check resolution for aliases bound to `as`-cast returns: the cast target type is
   known at translate time, so `a is T` reduces to `a IS NOT NULL` when T conforms (incl. the
   QA-003 FHIR string-family map for unqualified targets) and `FALSE` otherwise. Without this,
   `is FHIR.code` fell through to the resourceType strategy (`json_extract_string('final',...)`
   → malformed-JSON crash).

NOTE (self-inflicted, caught by recovery gate): first version emitted a second `patient_id`
column, breaking 14 scalar-subquery sites ("Subquery returns 2 columns"); correlation already
flows through the inner FROM alias, so the extra column was removed.

## QA-102 (MEDIUM) — RESOLVED. Descendants/Children over nested list literals
Spec: CQL 1.5 §Children/§Descendants — a list source invokes the operator per element and
flattens (primitive elements have no children → `[]`), never a translation/binder error.
Root cause: list literals lowered to SQL arrays; `[1, [2, 3]]` is untypable in DuckDB →
"Cannot deduce template type 'T'". Fix: `_functions.py::_translate_structural_traversal_arg/_value`
serialize ListExpression traversal arguments (and tuple-valued list elements) as
`json_array(...)` (recursively), which `cqlChildren`/`cqlDescendants` decode natively on both the
Python and native C++ paths. `Descendants({1, {2, 3}})` → `[]`; `Descendants({{ {a: 1} }, 2})` → `[1]`.

## QA-103 (HIGH) — OPEN, PRE-EXISTING, out of chunk. DQM conformance regression
14 DQM measures fail (32/47): binder "Subquery returns 2 columns" and unresolved
`urn:cql:code` valueset placeholders. Verified by bisect that this failure set is IDENTICAL with
every CQL-05 HISTORIAN edit disabled — introduced by sibling-chunk campaign edits (08-20 05:29-05:40
window: _operators.py/_lists.py/correlation.py/inference.py). Not fixed here: out of CQL-05 scope,
foreign in-flight work, single-writer discipline. Needs outer-orchestrator assignment.

## Files changed (this launch)
- fhir4ds/cql/translator/expressions/_query.py (nested-query element-value alias binding + static as-is check)
- fhir4ds/cql/translator/expressions/_core.py (Query-source alias → bare identifier)
- fhir4ds/cql/translator/expressions/_functions.py (json_array serialization for traversal args)
- fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py (+2 tests, 19 total)

## Validation
- test_structural_type_parity.py: 19/19 (native + forced-Python, parity asserted)
- Full conformance with this launch's fixes: ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706 — no regression from CQL-05 work. DQM 32/47 is the pre-existing QA-103 blocker
  (identical with this launch's edits disabled).

# QA Handoff — SOF-VD-04 (EXPLORER), iteration 1

Chunk: ViewDefinition.select.column.{collection,type,tag}. Personality: EXPLORER
(fuzz/boundary). Probes: /mnt/d/fhir4ds/.temp/qa/sof_vd04_explorer/{probe.py,probe2.py}.
All executed end-to-end through parse -> SQLGenerator -> DuckDB execution, native
extension + Python-fallback parity where behavior (not just parse/gen) differed.

## Probed and CONFORMANT
- Mixed-type multi-values with collection=true (component.value[x] = Quantity+Integer+
  String; extension.value = string+integer; contained resources): untyped mixed incl.
  complex errors "non-primitive outputs require column.type"; typed mixed errors at
  runtime with declared-type message; primitive-only mixed untyped returns string list
  (representation choice, spec-silent); contained typed Observation returns JSON list.
  PARITY native/py on all.
- Nested collection columns inside forEach and forEachOrNull at depth: correct typed
  lists, empty lists for absent element-level collections, null-preserved wrapper row
  per the pinned SOF-VD-05 step-3 doctrine; plain forEach absent -> zero rows.
- Type URI forms: 'String'/'STRING'/'quantity' (case variants) rejected with supported-
  type list (correct: FHIR type names case-sensitive); version-piped canonical
  '…/string|4.0.1' rejected at generation as element-ID 'string|4.0.1' vs resource
  (defensible, canonical-with-pipe is not a v2 column.type form); urn:uuid / urn:oasis
  forms rejected as unsupported; 'Observation.component.value' and fragment form parse
  and behave as complex element-ID types (same-resource misdeclaration pinned INTENDED
  by the HISTORIAN launch).
- collection=true element typing: integer list [100,90,80], decimal list [90.0,95.0],
  string list at depth, backbone element-ID list of JSON — all correct, PARITY.
- Tags at volume: 125 tags incl. duplicate names, 'ansi/type' + 'type' namespace pair,
  unicode emoji/CJK names+values, 5000-char value, 300-char name — all parse, execute,
  and to_dict round-trip preserved; tags never alter output. Empty-string name/value
  rejected (correct).
- unionAll branch column matching: collection flag mismatch (true vs unset, true vs
  false) rejected at generation with schema-diff message. Conformant.
- collection=true on %constant path: ['const'] / singleton scalar when false. Conformant.
- Empty-collection output for absent fields at depth: [] for collection columns, NULL
  row via forEachOrNull wrapper. Conformant.

## Issues
- QA-001 (LOW, OPEN): whitespace-only tag.name/tag.value (e.g. ' ') rejected at parse,
  but the canonical v2 StructureDefinition defines them as string 1..1 with NO
  minLength — ' ' is spec-valid metadata. Root cause: ColumnTag reuses
  validate_required_string (fhir4ds/viewdef/types.py:47) whose whitespace-stripping
  doctrine is right for FHIRPath-bearing fields (column.path, where.path) but overreach
  for opaque tag metadata.

Zero CRITICAL/HIGH/MEDIUM issues. Baseline suites not yet rerun this launch (no code
changes made during QA; pre-fix state matches the committed tree that passed 2832/2832).

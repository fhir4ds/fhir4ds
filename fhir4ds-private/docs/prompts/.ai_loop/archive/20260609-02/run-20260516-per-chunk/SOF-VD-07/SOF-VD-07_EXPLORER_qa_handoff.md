# QA Handoff: SOF-VD-07 EXPLORER

Personality: EXPLORER
Iteration: 1
Scope: SQL-on-FHIR ViewDefinition `select.repeat`

## Spec Anchor

- SQL-on-FHIR v2 `ViewDefinition.select.repeat`: repeat path expressions are applied from the current context node, recursively reapplied to each result, and results from all depths/paths are unioned until no more matches are found.
- FHIRPath `repeat(projection)`: projection repeats while it yields new items; traversal should not stop at an implementation recursion limit for finite JSON trees.

## Probes Run

- Native C++ and forced Python fallback direct `fhirpath_repeat` parity for official-style `["item", "answer.item"]`.
- Duplicate-path and identical-sibling behavior probes.
- `$this` self-path termination probe.
- Filtered repeat expression probe using `item.where(text.exists())`.
- Raw JSON deep-recursion probes at depths 300, 800, 1100, 1500, and 2500 to avoid Python `json.dumps` masking the UDF behavior.

## Findings

- `QA-001` HIGH OPEN: forced Python fallback `fhirpath_repeat` silently returns an empty list for deeply nested raw JSON once Python recursion is exceeded. Native C++ returns the expected repeated nodes. This can make a valid `select.repeat` ViewDefinition drop all repeated rows on fallback.

## Evidence Summary

Command shape:

```sql
SELECT len(fhirpath_repeat(?::JSON, '["item"]'))
```

Using a raw `QuestionnaireResponse` JSON string with nested `item` depth 800:

- Native C++ registration: `801`, first `n0`, last `n800`
- Forced Python fallback registration: `0`

## Next Phase

Remediation should replace the Python fallback recursive DFS with an iterative traversal that preserves current preorder/path behavior, then add a native/fallback ViewDefinition regression using raw JSON input.

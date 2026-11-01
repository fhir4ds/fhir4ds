# QA Handoff - FP-12 EXPLORER Retry

## Scope

Retry driven by architect note for FHIRPath §5.8.2:
`descendants()` must be shorthand for `repeat(children())`, including complex
duplicate values that are semantically equal even when JSON object key order
differs.

## Probe

Updated and reran `.temp/qa/fp12_explorer_probe.py`, producing
`.temp/qa/fp12_explorer_probe_retry.log`.

The retry added:

```json
{"resourceType":"Patient","a":{"x":1,"y":2},"b":{"y":2,"x":1}}
```

and checked:

```fhirpath
descendants().count() = repeat(children()).count()
descendants().count()
```

## Finding

`ARCH-001` remains OPEN and is now independently reproduced by QA:

- Native/C++: `descendants().count()` returned 4 and equality to
  `repeat(children()).count()` returned `false`.
- Forced Python fallback: `descendants().count()` returned 3 and equality to
  `repeat(children()).count()` returned `true`.

This is a native-only parity/spec issue in the key-generation layer added for
repeat-style descendant de-duplication.

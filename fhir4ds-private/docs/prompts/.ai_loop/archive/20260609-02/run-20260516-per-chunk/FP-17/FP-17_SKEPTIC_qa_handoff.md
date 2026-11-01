# QA Handoff - FP-17 SKEPTIC

## Scope

FHIRPath §6.5 Boolean Logic: `and`, `or`, `not()`, `xor`, `implies`.

## Spec Anchor

Current HL7 FHIRPath spec says Boolean operator operands are first evaluated as Booleans using singleton evaluation, then three-valued logic propagates empty operands. Multi-item singleton Boolean evaluation signals an error. The spec also notes implementations may short-circuit for performance, but authors cannot rely on it and short-circuiting must not change semantics; `implies` may short-circuit when the left operand is false.

## Hypotheses Tested

1. Native C++ might treat a multi-item Boolean operand as empty instead of a singleton error.
2. Native and forced Python fallback might diverge on truth-table cells where the other operand determines the result (`true or empty`, `false and empty`, `empty implies true`).
3. `not()` might have different singleton behavior from binary Boolean operators.
4. Single non-Boolean nodes might be coerced through `toBoolean()` instead of singleton truthiness.
5. `implies` short-circuiting might hide right-side singleton errors when the left operand is false.

## Fresh Probes

Commands:

```bash
mkdir -p .temp/qa/fp17
python3 - <<'PY'
import json
from fhir4ds.fhirpath import evaluate
resource={"resourceType":"Patient","arr":[True,False],"t":True,"f":False,"s":"x","n":0,"one":1,"two":2}
exprs=['arr or t','arr and f','arr xor t','arr implies t','f implies arr','t implies arr','arr.not()','s or f','s and t','s.not()','n and t','one and t','two and t']
for e in exprs:
    try:
        print(e, '=>', evaluate(resource,e))
    except Exception as exc:
        print(e, 'ERR', type(exc).__name__, str(exc))
PY
```

Result: Python core raises `FHIRPathError` for multi-item Boolean operands except `f implies arr`, which returns `[True]` by the documented `implies` false-left short-circuit.

```bash
python3 - <<'PY'
import json, duckdb
from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import fhirpath_scalar, fhirpath_json_udf, fhirpath_bool_udf
resource=json.dumps({"resourceType":"Patient","arr":[True,False],"t":True,"f":False,"s":"x","n":0,"one":1,"two":2})
exprs=['arr or t','arr and f','arr xor t','arr implies t','f implies arr','t implies arr','arr.not()','s or f','s and t','s.not()','n and t','one and t','two and t']
con=duckdb.connect(config={'allow_unsigned_extensions': True})
loaded=register_fhirpath(con)
print('native_loaded', loaded, 'duckdb', duckdb.__version__)
for e in exprs:
    cpp=con.execute("SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_bool(?::JSON, ?)",[resource,e,resource,e,resource,e]).fetchone()
    py=(fhirpath_scalar(resource,e), fhirpath_json_udf(resource,e), fhirpath_bool_udf(resource,e))
    print(e, 'cpp=', cpp, 'py=', py)
con.close()
PY
```

Result: confirmed QA-001.

## Issues

QA-001 HIGH: Native C++ `collectionIsBool()` returned `false` for multi-item operands, making callers treat them like empty/unknown. This leaked concrete results for `arr or t`, `arr and f`, and `arr implies t`; forced Python fallback returned empty/NULL through singleton enforcement.

## Validation

Focused QA probes above only. Remediation must add native-vs-forced-fallback parity coverage and rebuild/copy the bundled native extension if C++ source changes.

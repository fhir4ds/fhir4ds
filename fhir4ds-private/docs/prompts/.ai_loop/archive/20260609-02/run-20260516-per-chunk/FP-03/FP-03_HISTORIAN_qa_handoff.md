# QA Handoff - FP-03 HISTORIAN

Scope: FHIRPath N1 §5.1 Existence functions across Python core/fallback and native DuckDB extension.

Normative checks used:
- §5.1.8-§5.1.12: subset/superset/distinct/isDistinct use `=` equality.
- §6.1.1: complex equality is recursive child-property equality; numeric equality permits Integer/Decimal comparison; quantity equality compares same dimensions even when units differ.

Findings:
- QA-001: Native C++ distinct/isDistinct treat equal JSON objects with different key order as distinct.
- QA-002: Python core/fallback distinct/isDistinct do not use FHIRPath equality for mixed numeric duplicates such as `1` and `1.0`.
- QA-003: Native C++ subsetOf/supersetOf/distinct do not use quantity equality for comparable units such as `cm` and `mm`.

Reproducers:
- `objs.distinct().count()` and `objs.isDistinct()` with `objs=[{"a":1,"b":2},{"b":2,"a":1}]`.
- `1.combine(1.0).distinct().count()` and `1.combine(1.0).isDistinct()`.
- `(1 'cm').subsetOf(10 'mm')` and `(1 'cm').combine(10 'mm').distinct().count()`.

Recommended fix:
- Route Python existence membership/distinctness through the existing equality implementation.
- Update native `fpValuesEqual()` to use structural yyjson equality for JSON objects/arrays and compatible-unit quantity equality, then keep the public bundled extension fresh after rebuild.

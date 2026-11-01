# QA Handoff - SOF-VD-02 SKEPTIC

## Scope

SQL-on-FHIR ViewDefinition constants: `constant`, `constant.name`, and
`constant.value[x]`, including parser, direct resolver, direct dataclass
generator input, serializer behavior, and DuckDB execution with substitution in
`where` and column paths.

## Spec Anchor

The current SQL-on-FHIR ViewDefinition logical model defines `constant` as
`0..*`, `constant.name` as `1..1 string` with `sql-name`, and
`constant.value[x]` as `1..1` over the primitive choice list
`base64Binary`, `boolean`, `canonical`, `code`, `date`, `dateTime`,
`decimal`, `id`, `instant`, `integer`, `integer64`, `oid`, `string`,
`positiveInt`, `time`, `unsignedInt`, `uri`, `url`, and `uuid`.
Constants are referenced in FHIRPath as `%[name]`.

## Fresh Probe

`.temp/qa/sof_vd02_skeptic_probe.py`

The probe verified all supported primitive choices, invalid primitive shapes,
missing/multiple `value[x]`, complex unsupported values, `%name` substitution
inside `where`, literal `%name` preservation inside FHIRPath string literals,
plural `constants`, duplicate names, undefined constants, direct generator
input, and serializer boundaries.

## Findings

1. `SOFVD02-SKEPTIC-001` HIGH: parser accepts legacy top-level `constants`
   even though the logical model field is singular `constant`.
2. `SOFVD02-SKEPTIC-002` HIGH: direct `resolve_constants_in_path()` leaves an
   undefined user `%name` in place with only a warning.
3. `SOFVD02-SKEPTIC-003` HIGH: duplicate constant names are accepted and later
   collapse to last-wins resolution.
4. `SOFVD02-SKEPTIC-004` HIGH: direct `Constant` objects bypass primitive
   value, supported `value_type`, and serializer validation that parser paths
   already enforce.

## Recommended Fix

Centralize constant validation in `types.py` and reuse it from parser,
`Constant.from_dict()`, `Constant.to_dict()`, `SQLGenerator._validate_constants`,
and `ConstantResolver` construction. Reject the known legacy `constants`
alias at parse time with an explicit error. Make undefined user constants raise
`ConstantResolutionError` in the direct resolver while preserving built-in
FHIRPath variables such as `%resource`.

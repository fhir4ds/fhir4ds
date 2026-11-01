# QA Handoff — SOF-VD-13 EXPLORER launch (2026-08-24)

Personality: EXPLORER (fuzzer/abuser). Chunk: SOF-VD-13 CanonicalResource/DomainResource inheritance, cnl-0/cnl-1, tag.name namespace, extra_fields.

## Probed (all against final tree, PYTHONPATH=/mnt/d/fhir4ds)
- cnl-1 exotic urls: `|`, `#`, `|#` combos, urn:uuid:, unicode host/path, 3000-char url, zero-width space, tab. Tab → correct uri lexical ParseError; `|`/`#` shapes parse + warn exactly once; warn-worthy url (`http://x/a|b`) generates SQL and executes end-to-end in DuckDB (row returned). Unicode/urn/long urls parse clean, no spurious warnings.
- cnl-0 edges: 'Ab', 255/256 chars (256 warns once), 'A' len-1 (warns once), 'A_' clean, digits-first and unicode-capital names ('1Ab','Éxample') pre-empted by sql-name ParseError (matches prior SKEPTIC pin).
- sql-name warning-vs-error distinction: parse time raises (ViewDefinition.name, Column.name, Constant.name all verified); permissive validate_view_definition surfaces the same as warnings.
- tag namespace: 'ansi/type' (slash) does NOT warn — SOF-VD-04 reserved-namespace note confirmed; 'plain' warns once; '/leading','a/b/c' no warn; empty tag name rejected at parse (correct 1..1 string).
- extra_fields adversarial: nested nulls, 100KB values, case-colliding keys ('Note','URL' vs known fields), numeric/None dict keys (impossible in JSON) — all preserved verbatim, to_dict() JSON-serializable, multi-round-trip clean.
- text.div retention: CDATA, entities (&amp;), xmlns namespaces, malformed xhtml, plain non-xhtml text — byte-for-byte retained, no validation (retention-only confirmed).
- Warning capture: validate_view_definition() is exported and returns warnings programmatically.

## Findings
- QA-001 LOW: cnl-0 first-char check uses unicode-aware str.isupper() instead of spec ASCII [A-Z]; only reachable via directly-constructed ViewDefinition objects (JSON path pre-empted by sql-name error). Evidence: ViewDefinition(name='Éxample') → sql-name warning only, no cnl-0 warning.
- QA-002 LOW: generate_view_sql() swallows validator warnings (not logged, not returned).

Everything else verified conformant. Baseline runs deferred to post-fix gate per PROC_VALIDATION.

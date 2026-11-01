# QA Handoff — SOF-VD-10 EXPLORER (iteration 1, 2026-08-23)

Personality: EXPLORER (fuzzer/abuser). Chunk: SOF-VD-10 cross-cutting
validation. Spec verified against canonical v2 SD
(git show upstream/releases:ig/2.0.0/StructureDefinition-ViewDefinition.json,
local /mnt/d/sql-on-fhir-v2) and official sof-js/src/validate.js; official
examples decoded from ig/2.0.0/Binary-*.json.

## Probes (all fresh, PYTHONPATH=/mnt/d/fhir4ds)
- Deep nesting: 1000/2000/100000-level nested selects (dict + JSON string
  inputs) — RAW RecursionError escapes parse_view_definition (QA-001).
  Malformed nested select (dict instead of array) → clean typed ParseError.
- Huge fan-out: 10000 columns parse+generate 0.94s; 10000 top-level selects
  parse+generate 12.1s — no crash, no pathological blowup.
- sql-name extremes: reserved words / unicode / 300-char / case — all match
  spec regex ^[A-Za-z][A-Za-z0-9_]*$. '_x' rejection is spec-correct.
- ALL 62 DuckDB/FHIR reserved words as column names: parsed, quoted, and
  EXECUTED end-to-end (native extension) — every value correct.
- Entry-point consistency: dict vs JSON string vs ViewDefinition.from_dict on
  invalid VDs (bad column name; resource='patient') → ParseError on all three.
- resource binding: 'patient'/'PATIENT'/' Patient'/'Patient '/123/None/list
  all rejected (case-sensitive ResourceType code binding — correct).
- fhirVersion: '4.0.1' accepted; ' 4.0.1', 401, bare string, 'x.y.z' rejected.
- constant name == column name collision: accepted — no spec/validator rule
  forbids it (INTENDED).
- tag name='name'/'value' meta-collision: accepted, round-trips through
  to_dict; bad tag shapes (numeric name, null value, unknown key, missing
  value) all typed-rejected.
- Error paths: Where[i].path carries index; column faults name
  element+field+invariant+value but not full select-tree JSON path (QA-003,
  LOW DEFERRED).
- Round-trip maximal VD: stable except valueDecimal Decimal doctrine (QA-002,
  LOW DEFERRED — extension of HISTORIAN QA-001: default=str serialization is
  NOT re-parseable; default=float IS).
- Type confusion: numeric/null/list/dict/bool at column.path/.name/.description,
  resource, status, url, forEach, where.path, constant.name — all typed
  ParseError.
- End-to-end execution: maximal VD (tags, constants, forEach, where, unionAll,
  collection) executes correctly on native engine
  (cols pid,gender,givens,family,is_smith,u; row p1 correct incl. is_smith
  'true'); constant substitution `id = %targetId` executes ('p1','true').
- Official v2 examples use resourceType
  "https://sql-on-fhir.org/ig/StructureDefinition/ViewDefinition" — parser's
  required value is CORRECT (my initial fixture was wrong, not the parser).

## Findings
- 0 CRITICAL / 0 HIGH / 1 MEDIUM.
- QA-001 MEDIUM OPEN: raw RecursionError escapes parse_view_definition on
  ~1000+ deep nested selects (both dict and JSON-string paths); mandate
  requires recursion safety and clear typed errors.
- QA-002 LOW DEFERRED (doctrine extension), QA-003 LOW DEFERRED,
  QA-004 LOW INTENDED (not-a-bug confirmations).

Reproducers: /mnt/d/fhir4ds/.temp/qa/probe_explorer.py, probe_exec.py,
probe2.py.

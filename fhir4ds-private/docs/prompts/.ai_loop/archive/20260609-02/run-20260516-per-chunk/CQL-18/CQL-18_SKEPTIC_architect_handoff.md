# Architect Handoff - CQL-18 SKEPTIC

QA quality: sufficient. The SKEPTIC pass targeted null semantics, duplicate
set semantics, Quantity equality, and the three DuckDB execution surfaces
instead of only happy paths. It also cross-checked official singleton-null
cases to avoid overcorrecting `includes null`, `included in null`, and
`IndexOf(..., null)`.

Structural result: healthy after remediation. The fix centralizes CQL list
element equality in pure SQL macros that run in forced Python fallback,
native-loaded registration, and no-Python/browser-style C++ plus pure SQL macro
runtime. Translator routing now uses the semantic helper surface instead of
DuckDB list built-ins where the built-ins have incompatible null or JSON-string
equality behavior. A final mixed-type edge was hardened so non-numeric scalar
element mismatches compare false without DuckDB implicit cast errors.

Issue status: 3 QA issues, all `VERIFIED`.

- `QA-001`: `Except` duplicate preservation fixed with CQL set de-duplication.
- `QA-002`: `Intersect` null-element dropping fixed with CQL null-equal set
  membership.
- `QA-003`: Quantity list membership/set/equality fixed through
  `quantityCompare(..., '==')`.

Recommended fix order: none remaining for this chunk. No `RETRY_QA` required.
The active workflow can clean-exit and return to the outer spec compliance
orchestrator for archival.

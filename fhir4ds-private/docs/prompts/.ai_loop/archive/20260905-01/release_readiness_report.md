# Release Readiness Report — fhir4ds-v2 0.0.13 (2026-08-26)

## 1. Build Status

| Artifact | Status |
|---|---|
| fhirpath native extension | REBUILT this campaign (restored FP-18 div/mod, 2^63 literals, named groups, inline flags, PCRE-$); md5 39bea478 verified identical across repo bundle / build repository / wheel / site-packages |
| cql native extension | Current (no sources newer than the 2026-08-23 binary); md5 c5b22d58 wheel == repo |
| Wheel | `dist/fhir4ds_v2-0.0.13-py3-none-any.whl` built via hatch with both bundled extensions |
| WASM build | DEFERRED to docs_audit (directives allocate the wasm-demo/website sequence there; e2e runs after the website state is updated) |

## 2. Artifact Gate

- **Wheel metadata**: Version 0.0.13; `duckdb==1.5.2`, `numpy`, `pint>=0.21.0`;
  **medterm4ds>=0.0.3,<0.0.4 ships on BOTH extras** (`terminology`, `ner`
  with `[extraction]`) — the directives' key bound verification. Both native
  artifacts bundled; md5 parity with repo.
- **Clean install**: fresh venv, non-editable wheel install; import resolves
  to the venv site-packages; `__version__ == 0.0.13`; `pip check` clean.
- **C++ extension proof**: `register(con)` → `{"fhirpath_cpp": True,
  "cql_cpp": True}`; representative native functions executed
  (fhirpath_text 'B', fhirpath_number 4.5, quantityValue 3.0,
  cql_valueset_cache_clear/add/size=1, in_valueset).
- **Public API matrix**: create_connection(), create_connection(valueset_cache=…),
  register(con), register(con, valueset_cache=…), repeated register — all OK
  in the clean environment.
- **Hostile collision**: pre-existing `fhirpath_text` macro — registration
  does not crash; both extensions still load.
- **Unsupported DuckDB probe**: forced `duckdb==1.4.2` (wheel's exact
  `duckdb==1.5.2` pin correctly blocks a normal install — resolver conflict
  itself is a pass); with --no-deps, both extensions report False and the
  Python fallback serves `fhirpath_text` correctly — no crash.
- **Dual-Python CI invocation (post-bump)**: leg 3.10 = 3316 passed / 2
  skipped; leg 3.11 with **orjson 3.12.0** = 3316 passed / 2 skipped. The
  orjson depth-limit recovery probed directly on both spellings (3.11.9
  "recursion depth" + 3.12 "depth limit") — the 4f7de65b fix verified live
  on both legs.

## 3. Test Coverage

- **Unit**: focused artifact suites (UDF registration guard, terminology
  plumbing, sources, version constants) 219/219 with plugins disabled.
- **E2E (Playwright)**: deferred to immediately after docs_audit's website
  updates (testing the pre-update website would validate stale state);
  docs_audit's report will carry the e2e result.
- Campaign totals (recorded in ARCHIVE_LOG): 22 fixes, each with focused
  reproducer + suite + gate.

## 4. Conformance Report (Phase 4 gate, verbatim)

```
ViewDefinition            | 144      | 144      |  100.0%
FHIRPath (R4)             | 935      | 935      |  100.0%
CQL                       | 1706     | 1706     |  100.0%
DQM (QI Core 2025)        | 47       | 47       |  100.0%
OVERALL COMPLIANCE        | 2832     | 2832     |  100.0%
```

Known upstream fixture accuracies (CMS1017 92.9%, CMS135 91.4%, CMS145
96.1%, CMS157 70.0%) unchanged — no regression, no improvement.

## 5. Final GO / NO-GO Recommendation

**GO** — all four conformance suites PASS at the 2832/2832 baseline, the
artifact gate is fully green (metadata, both-extras medterm bound, clean
install, C++ proof, API matrix, collision, unsupported fallback, dual-leg
CI), and no blockers remain. Two tracked conditions, neither release-
blocking: (1) WASM wheel swap + website e2e execute in docs_audit per the
directives' sequence; (2) QA-018 (5 pre-existing lost-work parity tests,
outside the 2832 gate and outside the CI invocation's suite set) is
carried for Joel with the release-incident write-up in the evolution
architect handoff.

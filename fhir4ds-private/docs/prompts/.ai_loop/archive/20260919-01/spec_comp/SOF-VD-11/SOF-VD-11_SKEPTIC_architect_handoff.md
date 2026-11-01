# Architect Handoff — SOF-VD-11, iteration 1 (2026-08-23)

## Golden standard (chunk scope: View Runner + IG Examples)
1. Runner surface = parse_view_definition → SQLGenerator.generate → DuckDB
   execute; no hidden second execution path. VERIFIED (spec suite + probes).
2. All published 2.0.0 IG example VDs must parse, generate, execute, and
   reproduce documented expected tables. VERIFIED (5/5; PatientDemographics
   expected table reproduced exactly).
3. Column type coercion must be sane and identical across native/fallback
   engines. VERIFIED (INTEGER/BIGINT/DOUBLE/BOOLEAN/VARCHAR/JSON/VARCHAR[]);
   date/dateTime as VARCHAR is fixture-pinned (spec_tests assert strings).
4. No silent performance downgrades without accurate surfacing. QA-001 fixed.
5. spec_tests snapshot parity reportable without re-sync. NO DRIFT (22/22 md5).

## Fix audit (QA-001)
- Change is confined to the failure-logging branch of
  `_try_load_bundled_cpp_extension`; control flow (return False → Python
  fallback registration) unchanged; warning is actionable and accurate.
- No new silent fallback introduced; one removed (dead retry). Sound.
- Test asserts both the fallback functionality and the surfacing. Good.

## QA Enforcer Gate
QA coverage vs mandate: runner entry points (probed, contracts verified),
IG examples end-to-end + published expected tables, array unrolling
(address, name.where().first(), component), filtered views (top-level where),
type coercion + dual-engine parity, 144-suite fresh run, upstream drift
check (byte-level), parser/generator/exec agreement. Forward-drift of the
IG example surface (3.0.0-ballot resourceType form) correctly reported,
not actioned. No laziness detected. RETRY_QA: false.

## Exit
Zero non-terminal CRITICAL/HIGH/MEDIUM issues; iteration 1 >= min (1).
Exit CLEAN.

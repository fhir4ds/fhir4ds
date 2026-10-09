# Run-History Pane — Design (parity-build item 2)

Status: DESIGN FOR CONDUCTOR REVIEW — do not implement before approval.

## 1. Primary usage mode (proposed)

**Debug-compare** is the primary mode; audit-trail and replay ride along
as capabilities, not as the headline.

Rationale: the devserver's existing loops (cell runs, measure runs, test
runs, VD runs) already surface their *latest* result only. The recurring
pain is "it was green 10 minutes ago — what changed?" — which is a
compare question (library text vs. then, dataset vs. then, SQL vs. then),
not an audit question. Replay (re-execute a past event against the
current kernel) is a natural secondary action once the event record
exists, and audit-trail (who ran what when) is nearly free metadata we
should capture but not build UI around (this is a local dev tool, no
multi-user audit requirements).

## 2. Event scope

One event per logical execution:

| kind    | target                          | trigger                          |
|---------|---------------------------------|----------------------------------|
| cell    | `<library>/<cell define>`       | Run cell / Run all               |
| measure | `<measure name>`                | MeasurePane "Run measure"        |
| test    | `<measure name>`                | ExpectedResultsPane "Run tests"  |
| view    | `<view name or inline>`         | VdPane "Run"                     |

Evaluate/translate-only calls are NOT logged (they don't produce
comparable outcomes; measure/test runs already cover the interesting
evaluations).

## 3. Per-event capture

```json
{
  "id": "evt-1730123456789-0007",
  "ts": "2026-10-28T14:30:56.789Z",
  "kind": "measure",
  "target": "CleanroomMeasure",
  "status": "pass" | "fail" | "error",
  "duration_ms": 412,
  "row_count": 12,            // rows returned / patients evaluated
  "summary": { "initial-population": 2, "denominator": 2 },  // kind-specific
  "params": { "Measurement Period": "..." },                 // run params if any
  "library_sha": "sha256:...",   // hash of the CQL text actually run
  "sql_sha": "sha256:...",       // hash of the emitted SQL (SQL ref, not body)
  "error": "..."                  // first diagnostic when status=error
}
```

SQL/library bodies are NOT embedded in the log (cap friendliness); the
SHA pair + the workspace's git-ignored nature means "compare" links to
whatever the user has in the editor. Optional follow-up if the conductor
wants full replay fidelity: store the library TEXT (bounded, CQL is
small) but never the SQL body (large); SQL can be regenerated from
library + params deterministically.

## 4. Persistence

- File: `<workspace>/.runlog.jsonl` — one JSON line per event.
- Append-only; capped at **500 events / 256 KB**, whichever first; on
  overflow, prune oldest third (keeps writes O(1), avoids a rewrite per
  append until prune).
- Loaded on server start, appended on each run, served via
  `GET /api/runs` (list, newest first, `?kind=&limit=` filters).
- `DELETE /api/runs` clears the log (explicit user action from the pane).
- Rationale for file-per-workspace: matches the existing conventions
  (measures/, valuesets/, expected store all live in the workspace) and
  survives kernel restarts, which is the whole point of history.

## 5. UI

New icon-rail section **History** (8th tile, alt+8; slide-out entry under
a new "History" h2 — fits the item-6 nav unchanged):

- List: newest-first rows `time · kind badge · target · status dot ·
  duration · row count`; click a row to expand the event's summary +
  params inline.
- Filter chips: all / cell / measure / test / view (client-side).
- Actions per row:
  - **Reopen**: for measure/test/view events, re-selects the target in
    the workspace (open the library/measure/VD) so the user can re-run —
    full re-execution with the *stored* params is a follow-up toggle if
    the conductor wants it (primary mode is debug-compare, and compare
    wants current inputs, not blind replay).
  - **Copy SQL ref**: copies `sql_sha` (cheap; ties into Show SQL).
- Empty state: "No runs yet — history starts with your first run."

## 6. Open questions for the conductor

1. Primary mode OK as debug-compare (reopen-target, not blind replay)?
2. Cap 500 events / 256 KB reasonable, or smaller/larger?
3. Store library TEXT in events for exact replay, or SHA-only (proposed)?
4. History as an 8th nav tile (alt+8) — or fold under Tests section?

— end of design —

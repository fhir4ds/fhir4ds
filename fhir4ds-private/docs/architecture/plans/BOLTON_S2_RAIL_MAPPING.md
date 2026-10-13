# c-wasm-bolton S2 Gate Artifact — Icon-Mapping Table (single adaptive rail)

Per FDD v2 §4.6 + Muse: ONE rail, stable order both modes. Core section
always active; Cleanroom section capability-gated (entries ALWAYS visible,
locked entries disabled with remedy). This table is the migration contract
from the dev-server icon rail to the wasm product rail.

| # | Rail item (product) | Glyph | Dev-server origin (NavSection / pane) | Standalone state | Connected state |
|---|---------------------|-------|----------------------------------------|------------------|-----------------|
| — | *Core section (always active)* | | | | |
| 1 | CQL | ✏️ | playground editor pane | active (today's editor) | active (cell mode arrives S3) |
| 2 | Data | ▤ | `datasets` (DatasetPane) | active — Upload/inline tab only | active — Workspace files + Upload tabs |
| 3 | SQL | 📄 | SQLOutput pane | active | active (+ runs/sql sha history S2b) |
| 4 | Viewer | 🧑 | PatientDataViewer pane | active | active |
| — | *Cleanroom section (capability-gated, stable position)* | | | | |
| 5 | Libraries | ❯ | `libraries` slide-out | disabled + remedy ("requires a connected server — run `fhir4ds dev`") | active: file tree, add-path, watcher badges |
| 6 | Valuesets | ◈ | `terminology` slide-out (VS list) | disabled + remedy (inline paste stays in editor affordances) | active: workspace VS list + import (full terminology S4) |
| 7 | Measures | ✓ | `tests` slide-out (MeasurePane/Expected) | entry visible, interior hidden | active: scaffold/run/compare/baselines/expected |
| 8 | Terminology | ⌘ | `terminology` import + settings | entry visible, interior hidden (S4) | active: VSAC/UMLS/FHIR import + status (S4 wires fully) |
| 9 | History | ⏱ | RunHistoryPane | disabled + remedy (session-local note) | active: persistent runlog + runs/sql |
| — | *Retired from rail (kept as tabs/dialogs)* | | | | |
| — | Builder | ✚ | `builder` slide-out | stays the existing Builder TAB (wasm-native; no rail entry needed) | + "save to workspace" action when connected |
| — | Views | ▦ | `views` slide-out | merges into Data (ViewDefinition files are data-adjacent; S2 renders list only when connected) | active under Data tab |
| — | Settings | ⚙ | `settings` slide-out | stays the existing Header/settings affordance | + terminology config dialog (S4) |

## Rules locked by this table

1. ORDER IS FROZEN: the 9 entries above never reorder between modes; the
   core/cleanroom section split is visual only (subheader).
2. Standalone NEVER hides a cleanroom entry — disabled + remedy only
   (FDD hybrid rule); heavy interiors (Measures/Terminology) render a
   one-line empty state, not fake panels.
3. Builder/Views/Settings do NOT get rail entries in the product UI
   (they were slide-outs in dev-server; the product shell keeps tabs and
   header affordances). This is the simplification Muse endorsed (6-item
   cleanroom rail + 4-item core).
4. Alt+1..9 keyboard shortcuts follow the product order above.
5. Watcher events (connected): `changed` → badge on Libraries/Valuesets
   (per-file dot); `data-hint` → banner on Data with restart affordance
   (locked decision 4: data changes never auto-reload the kernel).

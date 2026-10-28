# FEATURE: ViewDefinition Form Editor (cleanroom views pane) — S29 follow-up

Date: 2026-10-28 · Branch: `feat/vd-form-editor` (off `main` @ `d24e9fc4`,
post-v0.0.19) · Backlog: conductor.md "views pane form editor"

## 1. Problem

The cleanroom's Views pane edits ViewDefinitions as raw JSON in a textarea
(`ViewPane.tsx` custom mode / `vd-editor` testid). Hand-authoring VD JSON is
error-prone: sql-name rules, `column.path`/`name` required pairs, resource
typo's, status codes. The Resource Builder (S29) proved the form-editor
pattern — schema-driven Form ⇄ Raw switch with a LOSSLESSNESS GUARD
(`formRoundTripLosses`) that blocks Form-mode entry when the JSON uses
constructs the form cannot represent exactly. Views get the same treatment.

## 2. Design

### 2.1 Where it lives — TWO-LEVEL control (Muse #1)

ViewPane's existing single toggle already uses "Form" for the DERIVED
("From Measure") surface; adding a second "Form" inside Custom would make
one word mean two things. The control becomes a hierarchy:

- **Level 1 — Source** (segmented, replaces the current Form/Text toggle):
  `[ From Measure | Custom ]`.
- **Level 2 — Custom presentation** (visible only in Custom mode, same
  `mode-switch` widget + labeling convention as the Resource Builder —
  the label names the CURRENT state): `Form ⇄` / `Raw ⇄`.
  - **Raw** = the current textarea, unchanged. Always available.
  - **Form** = `VdForm` (new `src/components/VdForm.tsx`): top-level
    scalar fields + ONE editable table over the single root select's
    columns.

Derived ("From Measure") mode is otherwise untouched.

### 2.2 Form schema (first-class vs passthrough vs blocked)

First-class form fields (the form OWNS these keys in the emitted JSON):

| Field | Control | Notes |
|---|---|---|
| `name` | text input | sql-name validated on commit (regex `^[A-Za-z][A-Za-z0-9_]*$`), empty = absent |
| `resource` | select | KNOWN_FHIR_RESOURCE_TYPES (159), free-text fallback for unknown values (sublabel "unknown") |
| `status` | select | draft/active/retired/unknown + "— absent —" |
| `select[0].column[]` | table | rows: name, path, type (dropdown: string/integer/decimal/boolean/date/dateTime/code + absent), collection (binary checkbox), ↑/↓ reorder, remove ×; "+ add column" appends an empty row |

**BLOCKING constructs** (Muse #2 — the clean single-select rule): the Form
editor is strictly for SINGLE-SELECT ViewDefinitions. Entering Form mode
is blocked (before any round-trip check) when the VD has:
- `select.length > 1` (multi-branch cross joins),
- a nested `select[0].select` or `select[0].unionAll`,
- `joins` (non-empty),
- or `repeat` on the root select (recursion is inherently non-tabular).

Rationale: these change the effective output schema in ways a flat column
table hides; editing `select[0]` while `select[1]` is invisible invites
confusion even when passthrough is lossless. The block message names the
construct ("multi-select ViewDefinitions must be edited in Raw mode").

**PASSTHROUGH constructs** (never edited, preserved verbatim, surfaced in
the banner §2.3.1): `select[0].forEach`/`forEachOrNull`/`where`, root
`where`, `constants`, and all other top-level keys (id/url/version/title/
profile/fhirVersion/meta/resourceType/extra_fields).

### 2.3 The guard (the point of the feature)

Two layers:

1. **Structural block** (§2.2 list) — fast, names the construct.
2. **`vdFormRoundTripLosses(json): string[]`** — mirrors
   `formRoundTripLosses`: `jsonToVdForm → vdFormToJson` must reproduce
   the input canonically; any key that differs (added/removed/changed,
   recursively) is listed as a HUMAN-readable path (Muse #5): columns are
   named — `column 'status' (index 3)` — top-level keys are bare
   (`constants`), and known constructs get a plain-language reason
   ("joins are not supported in Form mode"). Flipping Raw → Form is
   BLOCKED with the builder's exact error shape ("the form can't
   represent this exactly (…) — stay in Raw mode or simplify those
   fields"). Raw is always one click away and the guarded flip NEVER
   mutates the text.

Canonicalization rules (Argon): sort OBJECT keys only — never arrays
(column order is semantic); skip `undefined`-valued keys before diffing;
`1` vs `1.0` normalize via JSON.stringify leaves. EMIT order is human
FHIR order (resourceType, id, name, status, resource, …passthrough,
select), not sorted — sorting lives only inside the compare.

Form edits are total over the form-owned keys: changing a field rewrites
that key in the emitted JSON; the passthrough bag (everything else) is
merged back verbatim per level (INV-5 pattern).

### 2.3.1 Scope pill + preserved-constructs banner (Argon A/D, Muse #4)

Non-column constructs that ARE losslessly representable do not block, but
are surfaced CONTEXTUALLY, not as one jargon dump:

- **Scope pill on the column-table header** — when `select[0]` carries a
  `forEach`/`forEachOrNull`, the table header reads
  `Columns (evaluated per item in: <expr>)`, tying the iteration scope to
  the rows being edited.
- **Calm info pill** above the form, passive voice:
  `Preserved untouched: 2 filters · 1 constant` (root `where` count +
  `constants` count + `repeat` when present). No AST paths, no "Raw"
  alarm language.

Data-loss cases still BLOCK per §2.3.

### 2.4 Table → JSON mapping

The column table IS `select[0].column` (a 1:1 projection — same order,
reorder arrows rewrite it; no re-sorting). Emitting: rows map to
`{name, path}` + optional `type`/`collection`; EMPTY-STRING fields are
omitted (so a raw `{name:"foo"}` with no path round-trips) and a row
with BOTH name and path empty is dropped (half-typed drafts allowed while
editing; the flatten run surfaces validation). `collection` renders as a
BINARY checkbox (`checked = collection === true` — Muse #3; no tri-state
cycling) while the form STATE keeps absent vs explicit-false vs true so
an untouched `"collection": false` in raw survives round-trip verbatim;
user clicks write the key explicitly. Prefill: every existing column
becomes a row; columns with keys outside the modeled set (description,
tag) get a per-row "extra fields preserved" badge (hover tooltip lists
the preserved key/value pairs — Muse #7) and those keys are carried
through verbatim.

### 2.5 Persistence

ViewPane is stateless over the VD today (custom text lives in App-level
state via the view tab). The form flips on the CURRENT parsed text;
committing from Form mode writes the emitted JSON back through the
existing custom-VD text path, so run history, derivation, and flatten
behave identically.

### 2.6 Day-one flow: Copy from Measure (Muse #6)

Switching to Custom with an EMPTY draft seeds it from
`buildDerivedView(measure, overrides)` (the same derived VD the From
Measure mode renders), so a clinical author starts from the measure
populations and adds/removes columns rather than a blank page. The seed
happens once per empty-draft entry; existing custom text is never
overwritten. The seeding is visible in Raw mode as ordinary JSON.

## 3. Slices

1. **S1 `vdForm.ts` pure helper** — types + `jsonToVdForm`/`vdFormToJson`/
   `vdFormRoundTripLosses` + structural `vdFormBlockedReasons` + sql-name
   validation + column-naming path formatter; vitest round-trip
   invariants (lossless on the modeled subset incl. explicit-false
   collection + description/tag passthrough; loss-detected on malformed
   column entries; blocked on each §2.2 construct).
2. **S2 `VdForm.tsx` component + ViewPane wiring** — two-level control
   (§2.1), blocking guard, fields + column table (reorder, badges,
   tooltips), scope pill + preserved pill, Copy-from-Measure seed;
   commit-on-edit into the custom VD text; component tests via vitest.
3. **S3 journey tests + e2e** — Playwright journeys written from THIS
   plan's own words (§2.1–§2.6): edit name in form → JSON updates; VD
   with joins → Form blocked with a named reason; Raw always available;
   table row add/remove/reorder round-trips; explicit-false collection
   survives; forEach VD shows the scope pill; Copy-from-Measure seeds an
   empty custom draft. Full cleanroom gates.

## 4. Verification

vitest (unit round-trips) · `tsc` + `npm run build` · cleanroom e2e
(vite preview :5176) · design gates before implementation (done, §5) ·
journey-test doctrine: every plan promise in §2 pinned by a journey test
before the slice is called complete.

## 5. Review record

- **Second opinion (Gemini 4 Argon, 2026-10-28)**: endorsed
  select[0]-only cut, hard BLOCKING UX, and the v1 field set; required
  the preserved-constructs banner, JSON-path loss messages,
  undefined-skip + object-keys-only canonicalization, human-order emit,
  explicit-false collection preservation. Integrated.
- **Muse design gate (2026-10-28)**: Muse model DOWN (UnknownError /
  model-not-found on both invocation paths); used FLEET_SO_MENU fallback
  `gemini-flash` in the Muse role per the skill's failure policy.
  Verdict **APPROVE-WITH-CHANGES**, 7 findings, all integrated:
  (1-HIGH) two-level control — no second "Form" word; (2-HIGH) clean
  single-select blocking rule replacing the passthrough-vs-block
  contradiction; (3-HIGH) binary collection checkbox (state still
  preserves explicit false); (4-MED) scope pill + calm preserved pill
  instead of AST-path banner; (5-MED) column-naming loss messages;
  (6-MED) Copy-from-Measure day-one seed; (7-LOW) reorder arrows +
  extra-fields tooltip.

## 6. Explicitly out of scope

Editing nested selects beyond the single root select's columns;
constants editor; joins editor (blocked → Raw by design); migrating the
derived ("From Measure") mode; viewing-room app.

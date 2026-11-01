/**
 * ViewDefinition form model — FEATURE_VD_FORM_EDITOR.md §2.2–§2.4.
 *
 * The form is a projection of a ViewDefinition: it owns `name`,
 * `resource`, `status`, and the single root select's `column` table.
 * Everything else is passthrough, preserved verbatim per level (INV-5
 * pattern from resourceForm.ts). Two guard layers protect Raw → Form:
 *
 * 1. vdFormBlockedReasons — structural block: the form is strictly for
 *    SINGLE-SELECT VDs (no multi-branch selects, nested selects,
 *    unionAll, joins, or repeat). Named, plain-language reasons.
 * 2. vdFormRoundTripLosses — jsonToVdForm → vdFormToJson must reproduce
 *    the input canonically; differing keys are listed with HUMAN paths
 *    (columns are NAMED: "column 'status' (index 3)").
 *
 * Canonicalization (Argon review): sort OBJECT keys only — never arrays;
 * skip undefined-valued keys; 1 vs 1.0 normalize via JSON.stringify.
 * Emit order is human FHIR order, not sorted.
 */

/** sql-name (ViewDefinition.name / Column.name): ^[A-Za-z][A-Za-z0-9_]*$ */
export const SQL_NAME_RE = /^[A-Za-z][A-Za-z0-9_]*$/;

export function isValidSqlName(v: string): boolean {
  return SQL_NAME_RE.test(v);
}

/** Column.type dropdown options (§2.2; absent = no type hint). */
export const COLUMN_TYPE_OPTIONS = [
  "string",
  "integer",
  "integer64",
  "decimal",
  "boolean",
  "date",
  "dateTime",
  "time",
  "code",
  "uri",
] as const;

/** ViewDefinition.status publication codes (draft/active/retired/unknown). */
export const VD_STATUS_OPTIONS = ["draft", "active", "retired", "unknown"] as const;

/**
 * Tri-state collection in form STATE (absent / explicit-false / true):
 * the UI renders a binary checkbox; the state distinction exists only so
 * an untouched explicit `"collection": false` round-trips verbatim
 * (Muse #3: users never cycle three states).
 */
export type CollectionState = "absent" | "false" | "true";

export interface ColumnRow {
  /** client identity (stable across reorder, like builder _keys) */
  key: string;
  name: string;
  path: string;
  type: string; // "" = absent
  collection: CollectionState;
  /** keys outside the modeled set (description, tag, …) — verbatim */
  extras: Record<string, unknown>;
}

export interface VdFormState {
  name: string;
  resource: string;
  status: string; // "" = absent
  columns: ColumnRow[];
  /** root-select non-column children, preserved verbatim */
  selectPassthrough: Record<string, unknown>;
  /** top-level keys the form does not model, preserved verbatim */
  passthrough: Record<string, unknown>;
}

let keySeq = 0;
function newKey(): string {
  keySeq += 1;
  return `vc${keySeq}`;
}

/** §2.2 structural block: single-select VDs only. Plain-language reasons. */
export function vdFormBlockedReasons(json: Record<string, unknown>): string[] {
  const reasons: string[] = [];
  const selects = Array.isArray(json.select) ? json.select : null;
  if (!selects || selects.length === 0) {
    reasons.push("the ViewDefinition has no select structure to edit");
    return reasons;
  }
  if (selects.length > 1) {
    reasons.push(
      "multi-select ViewDefinitions must be edited in Raw mode",
    );
  }
  const first = selects[0];
  if (
    typeof first === "object" && first !== null &&
    !Array.isArray(first)
  ) {
    const sel = first as Record<string, unknown>;
    if (Array.isArray(sel.select) && sel.select.length > 0) {
      reasons.push("nested selects must be edited in Raw mode");
    }
    if (Array.isArray(sel.unionAll) && sel.unionAll.length > 0) {
      reasons.push("unionAll branches must be edited in Raw mode");
    }
    if (sel.repeat !== undefined) {
      reasons.push("repeat (recursive traversal) must be edited in Raw mode");
    }
  }
  if (Array.isArray(json.joins) && json.joins.length > 0) {
    reasons.push("joins are not supported in Form mode");
  }
  return reasons;
}

function prefillColumn(entry: unknown): ColumnRow {
  // Non-object or array column entries cannot be modeled — keep the row
  // with the raw value in extras so the round-trip guard reports it.
  if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
    return {
      key: newKey(),
      name: "",
      path: "",
      type: "",
      collection: "absent",
      extras: { __raw__: entry },
    };
  }
  const col = entry as Record<string, unknown>;
  const modeled = new Set(["name", "path", "type", "collection"]);
  const extras: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(col)) {
    if (!modeled.has(k)) extras[k] = v;
  }
  const collection: CollectionState =
    col.collection === true
      ? "true"
      : col.collection === false
        ? "false"
        : "absent";
  return {
    key: newKey(),
    name: typeof col.name === "string" ? col.name : "",
    path: typeof col.path === "string" ? col.path : "",
    type: typeof col.type === "string" ? col.type : "",
    collection,
    extras,
  };
}

/** ViewDefinition JSON → form state (prefill). */
export function jsonToVdForm(
  json: Record<string, unknown>,
): VdFormState {
  const form: VdFormState = {
    name: typeof json.name === "string" ? json.name : "",
    resource: typeof json.resource === "string" ? json.resource : "",
    status: typeof json.status === "string" ? json.status : "",
    columns: [],
    selectPassthrough: {},
    passthrough: {},
  };
  const first = Array.isArray(json.select)
    ? (json.select[0] as Record<string, unknown> | undefined)
    : undefined;
  if (first && typeof first === "object" && !Array.isArray(first)) {
    const cols = Array.isArray(first.column) ? first.column : [];
    form.columns = cols.map((c) => prefillColumn(c));
    for (const [k, v] of Object.entries(first)) {
      if (k !== "column") form.selectPassthrough[k] = v;
    }
  }
  const modeled = new Set(["name", "resource", "status", "select"]);
  for (const [k, v] of Object.entries(json)) {
    if (!modeled.has(k)) form.passthrough[k] = v;
  }
  return form;
}

/** Human FHIR order for the emitted root object (§2.3 — not sorted). */
const EMIT_ORDER = [
  "resourceType",
  "id",
  "name",
  "status",
  "resource",
];

function emitColumn(row: ColumnRow): Record<string, unknown> | null {
  // A row with BOTH name and path empty is dropped (half-typed draft).
  if (row.name === "" && row.path === "") return null;
  const out: Record<string, unknown> = {};
  if (row.name !== "") out.name = row.name;
  if (row.path !== "") out.path = row.path;
  if (row.type !== "") out.type = row.type;
  if (row.collection === "true") out.collection = true;
  else if (row.collection === "false") out.collection = false;
  // extras merged back verbatim; __raw__ rows re-emit the raw value
  // wholesale (they can only exist mid-guard-fail, never after a pass).
  if ("__raw__" in row.extras) return row.extras.__raw__ as Record<string, unknown>;
  for (const [k, v] of Object.entries(row.extras)) {
    out[k] = v;
  }
  return out;
}

/** Form state → ViewDefinition JSON. */
export function vdFormToJson(form: VdFormState): Record<string, unknown> {
  const ordered: Record<string, unknown> = {};
  const put = (k: string, v: unknown) => {
    if (v !== undefined && v !== "") ordered[k] = v;
  };
  // Human-order keys first (values pulled from form/passthrough alike).
  const sources: Record<string, unknown> = {
    ...form.passthrough,
    name: form.name,
    status: form.status,
    resource: form.resource,
  };
  for (const k of EMIT_ORDER) {
    if (k in sources) put(k, sources[k]);
  }
  // Remaining passthrough keys (not already emitted), in their own order.
  for (const [k, v] of Object.entries(form.passthrough)) {
    if (!(k in ordered)) put(k, v);
  }
  const select: Record<string, unknown> = {};
  const column = form.columns
    .map(emitColumn)
    .filter((c): c is Record<string, unknown> => c !== null);
  if (column.length > 0) select.column = column;
  for (const [k, v] of Object.entries(form.selectPassthrough)) {
    select[k] = v;
  }
  ordered.select = [select];
  return ordered;
}

/** Canonical JSON for lossless comparison: object keys sorted, arrays
 * kept in order, undefined-valued keys skipped (Argon rules). */
function canonicalJson(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonicalJson).join(",")}]`;
  if (v && typeof v === "object") {
    const rec = v as Record<string, unknown>;
    const keys = Object.keys(rec)
      .filter((k) => rec[k] !== undefined)
      .sort();
    return `{${keys
      .map((k) => `${JSON.stringify(k)}:${canonicalJson(rec[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(v) ?? "null";
}

/**
 * Human-readable path for one differing top-level subtree (Muse #5):
 * columns are NAMED — "column 'status' (index 3)" — and column entries
 * that are not objects name the reason structurally.
 */
function humanPath(key: string, index: number, orig: unknown): string {
  if (key === "select") {
    const first = Array.isArray(orig)
      ? (orig[0] as Record<string, unknown> | undefined)
      : undefined;
    const cols = first && Array.isArray(first.column) ? first.column : [];
    const entry = cols[index];
    if (typeof entry === "object" && entry !== null) {
      const name = (entry as { name?: unknown }).name;
      if (typeof name === "string" && name) {
        return `column '${name}' (index ${index})`;
      }
    }
    return `column (index ${index})`;
  }
  return key;
}

/**
 * §2.3 guard: jsonToVdForm → vdFormToJson must reproduce the input
 * canonically. Returns HUMAN-readable loss descriptions; empty = safe
 * to flip into Form mode. Assumes the structural block (§2.2) already
 * passed — call vdFormBlockedReasons first.
 */
export function vdFormRoundTripLosses(
  json: Record<string, unknown>,
): string[] {
  const round = vdFormToJson(jsonToVdForm(json));
  const losses: string[] = [];
  const keys = new Set([...Object.keys(json), ...Object.keys(round)]);
  for (const key of keys) {
    const orig = json[key];
    const emitted = round[key];
    if (canonicalJson(orig) === canonicalJson(emitted)) continue;
    if (key === "select") {
      // Drill into the first select's column array for named paths.
      const origCols = Array.isArray(
          (json.select as Array<Record<string, unknown>> | undefined)?.[0]?.column,
        )
        ? ((json.select as Array<Record<string, unknown>>)[0]
            .column as unknown[])
        : [];
      const roundCols = Array.isArray(
          (round.select as Array<Record<string, unknown>> | undefined)?.[0]?.column,
        )
        ? ((round.select as Array<Record<string, unknown>>)[0]
            .column as unknown[])
        : [];
      const n = Math.max(origCols.length, roundCols.length);
      let namedAny = false;
      for (let i = 0; i < n; i++) {
        if (canonicalJson(origCols[i]) !== canonicalJson(roundCols[i])) {
          losses.push(humanPath(key, i, json.select));
          namedAny = true;
        }
      }
      // Non-column differences inside select[0] (e.g. dropped forEach).
      const origSel = (json.select as Array<Record<string, unknown>>)[0];
      const roundSel = (round.select as Array<Record<string, unknown>>)[0];
      const selKeys = new Set([
        ...Object.keys(origSel ?? {}),
        ...Object.keys(roundSel ?? {}),
      ]);
      for (const sk of selKeys) {
        if (sk === "column") continue;
        if (canonicalJson(origSel?.[sk]) !== canonicalJson(roundSel?.[sk])) {
          losses.push(`select ${sk}`);
          namedAny = true;
        }
      }
      if (!namedAny) losses.push("select");
    } else {
      losses.push(key);
    }
  }
  return losses;
}

/** §2.3.1 banner inputs: counts/expressions for the preserved pills. */
export function vdFormPreservedNotes(
  json: Record<string, unknown>,
): { scopeExpr: string | null; filters: number; constants: number } {
  const first = Array.isArray(json.select)
    ? (json.select[0] as Record<string, unknown> | undefined)
    : undefined;
  const scopeExpr =
    typeof first?.forEach === "string"
      ? first.forEach
      : typeof first?.forEachOrNull === "string"
        ? first.forEachOrNull
        : null;
  const rootWhere = Array.isArray(json.where) ? json.where.length : 0;
  const selWhere =
    first && Array.isArray(first.where) ? first.where.length : 0;
  const constants = Array.isArray(json.constants) ? json.constants.length : 0;
  return { scopeExpr, filters: rootWhere + selWhere, constants };
}

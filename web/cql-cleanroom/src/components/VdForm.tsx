import { useMemo } from "react";
import {
  COLUMN_TYPE_OPTIONS,
  VD_STATUS_OPTIONS,
  vdFormPreservedNotes,
  type ColumnRow,
  type VdFormState,
} from "../lib/vdForm";

/**
 * VdForm — the Form-mode editor for a custom ViewDefinition
 * (FEATURE_VD_FORM_EDITOR §2.2–§2.6). Renders ONLY after the structural
 * block and round-trip guard passed (ViewPane owns the guard UX); the
 * component itself is a controlled projection: every edit emits the full
 * JSON through onChange.
 *
 * Scope pill (§2.3.1) on the table header when the single select has a
 * forEach/forEachOrNull; calm preserved pill for filters/constants;
 * "extra fields preserved" badges with tooltips (Muse #7); binary
 * collection checkbox over tri-state state (Muse #3).
 */

let rowSeq = 0;
function newRow(): ColumnRow {
  rowSeq += 1;
  return {
    key: `row${rowSeq}`,
    name: "",
    path: "",
    type: "",
    collection: "absent",
    extras: {},
  };
}

export function VdForm({
  form,
  onChange,
  blockedNote,
}: {
  form: VdFormState;
  onChange: (next: VdFormState) => void;
  /** §2.2 structural-block note rendered above the form (rare). */
  blockedNote?: string | null;
}) {
  const notes = useMemo(() => vdFormPreservedNotes(emitDraft(form)), [form]);

  const setColumn = (key: string, patch: Partial<ColumnRow>) => {
    onChange({
      ...form,
      columns: form.columns.map((c) =>
        c.key === key ? { ...c, ...patch } : c,
      ),
    });
  };
  const moveRow = (index: number, delta: -1 | 1) => {
    const next = [...form.columns];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange({ ...form, columns: next });
  };

  return (
    <div className="vd-config vd-form" data-testid="vd-form">
      {blockedNote && (
        <div className="diag-row diag-error" data-testid="vd-form-blocked">
          {blockedNote}
        </div>
      )}
      {/* §2.3.1 preserved pill — passive voice, no AST jargon */}
      {(notes.filters > 0 || notes.constants > 0) && (
        <div className="diag-row diag-info" data-testid="vd-form-preserved">
          Preserved untouched: {notes.filters} filter
          {notes.filters === 1 ? "" : "s"}
          {notes.filters > 0 && notes.constants > 0 ? " · " : ""}
          {notes.constants} constant{notes.constants === 1 ? "" : "s"}
        </div>
      )}

      <div className="vd-form-fields">
        <label className="vd-form-field">
          <span>name</span>
          <input
            data-testid="vd-form-name"
            value={form.name}
            placeholder="sql-name (letters, digits, _)"
            onChange={(e) => onChange({ ...form, name: e.target.value })}
          />
        </label>
        <label className="vd-form-field">
          <span>resource</span>
          <input
            data-testid="vd-form-resource"
            value={form.resource}
            placeholder="Patient"
            list="vd-form-resource-options"
            onChange={(e) => onChange({ ...form, resource: e.target.value })}
          />
          <datalist id="vd-form-resource-options">
            {COMMON_RESOURCES.map((r) => (
              <option key={r} value={r} />
            ))}
          </datalist>
        </label>
        <label className="vd-form-field">
          <span>status</span>
          <select
            data-testid="vd-form-status"
            value={form.status}
            onChange={(e) => onChange({ ...form, status: e.target.value })}
          >
            <option value="">— absent —</option>
            {VD_STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* §2.3.1 scope pill ties iteration scope to the rows below */}
      <div className="vd-table-head">
        <h3>
          Columns
          {notes.scopeExpr && (
            <span
              className="vd-scope-pill"
              data-testid="vd-form-scope-pill"
              title="Column paths are evaluated against each item of this iteration"
            >
              evaluated per item in: <code>{notes.scopeExpr}</code>
            </span>
          )}
        </h3>
      </div>
      <table className="vd-columns" data-testid="vd-form-columns">
        <thead>
          <tr>
            <th>Column</th>
            <th>FHIRPath</th>
            <th>type</th>
            <th>coll.</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {form.columns.map((c, i) => {
            const extraKeys = Object.keys(c.extras);
            return (
              <tr key={c.key} data-testid={`vd-form-col-${i}`}>
                <td>
                  <input
                    data-testid={`vd-form-col-name-${i}`}
                    value={c.name}
                    placeholder="name"
                    onChange={(e) => setColumn(c.key, { name: e.target.value })}
                  />
                  {extraKeys.length > 0 && (
                    <span
                      className="vd-override-badge"
                      data-testid={`vd-form-col-extras-${i}`}
                      title={`${extraKeys.join(", ")}: ${JSON.stringify(c.extras)}`}
                    >
                      +{extraKeys.length} preserved
                    </span>
                  )}
                </td>
                <td>
                  <input
                    className="vd-path-input"
                    data-testid={`vd-form-col-path-${i}`}
                    value={c.path}
                    placeholder="path"
                    onChange={(e) => setColumn(c.key, { path: e.target.value })}
                  />
                </td>
                <td>
                  <select
                    data-testid={`vd-form-col-type-${i}`}
                    value={c.type}
                    onChange={(e) => setColumn(c.key, { type: e.target.value })}
                  >
                    <option value="">—</option>
                    {COLUMN_TYPE_OPTIONS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`column ${c.name || i} collection`}
                    data-testid={`vd-form-col-collection-${i}`}
                    checked={c.collection === "true"}
                    onChange={(e) =>
                      setColumn(c.key, {
                        // Binary checkbox; explicit write keeps the key
                        // present (false round-trips once authored).
                        collection: e.target.checked ? "true" : "false",
                      })
                    }
                  />
                </td>
                <td className="vd-row-actions">
                  <button
                    type="button"
                    aria-label={`move column ${c.name || i} up`}
                    data-testid={`vd-form-col-up-${i}`}
                    disabled={i === 0}
                    onClick={() => moveRow(i, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={`move column ${c.name || i} down`}
                    data-testid={`vd-form-col-down-${i}`}
                    disabled={i === form.columns.length - 1}
                    onClick={() => moveRow(i, 1)}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    aria-label={`remove column ${c.name || i}`}
                    data-testid={`vd-form-col-remove-${i}`}
                    title={
                      extraKeys.length
                        ? `Removing drops ${extraKeys.length} preserved field(s): ${extraKeys.join(", ")}`
                        : "Remove this column"
                    }
                    onClick={() =>
                      onChange({
                        ...form,
                        columns: form.columns.filter((x) => x.key !== c.key),
                      })
                    }
                  >
                    ×
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="builder-add-row">
        <button
          type="button"
          data-testid="vd-form-col-add"
          onClick={() => onChange({ ...form, columns: [...form.columns, newRow()] })}
        >
          + add column
        </button>
      </div>
    </div>
  );
}

/** Emit the current form (for preserved-note derivation only). */
function emitDraft(form: VdFormState): Record<string, unknown> {
  // Local re-implementation of the emit used by vdFormToJson to avoid a
  // circular import of the emit from the helper (which takes FORM state
  // directly) — cheap for note derivation.
  const select: Record<string, unknown> = {};
  const column = form.columns
    .filter((c) => c.name !== "" || c.path !== "")
    .map((c) => {
      const out: Record<string, unknown> = {};
      if (c.name !== "") out.name = c.name;
      if (c.path !== "") out.path = c.path;
      if (c.type !== "") out.type = c.type;
      if (c.collection === "true") out.collection = true;
      else if (c.collection === "false") out.collection = false;
      for (const [k, v] of Object.entries(c.extras)) out[k] = v;
      return out;
    });
  if (column.length > 0) select.column = column;
  for (const [k, v] of Object.entries(form.selectPassthrough)) select[k] = v;
  return { ...form.passthrough, resource: form.resource, select: [select] };
}

/** Common resources for the datalist (full 159-type list lives in the
 * Python metadata; the browser form keeps a curated day-one set with
 * free-text fallback for anything else). */
const COMMON_RESOURCES = [
  "Patient",
  "Observation",
  "Condition",
  "Encounter",
  "Procedure",
  "MedicationRequest",
  "Immunization",
  "ServiceRequest",
  "MeasureReport",
  "Questionnaire",
  "Coverage",
  "Specimen",
];

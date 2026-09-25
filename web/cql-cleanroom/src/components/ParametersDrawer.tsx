/**
 * Parameters drawer (editor column) — runtime parameter bindings for
 * the ENTRYPOINT library. Values flow through evaluate/run-tests/
 * explain to translation (set_parameter_binding). Declared names come
 * from the App's parse of the entrypoint CQL (detectParams twin).
 */

export interface ParamBinding {
  name: string;
  value: string;
}

export function detectParams(cqlText: string): string[] {
  const names: string[] = [];
  for (const m of cqlText.matchAll(/parameter\s+"([^"]+)"\s+([A-Za-z][A-Za-z0-9_<>\s]*)/g)) {
    if (!names.includes(m[1])) names.push(m[1]);
  }
  return names;
}

/** Parse a raw panel value into the engine's parameter shape.
 *  Interval<DateTime>-style params accept "start..end" or ISO "start/end"
 *  syntax; everything else passes as the plain string. */
export function coerceParam(raw: string): unknown {
  const v = raw.trim();
  // Interval forms: "A .. B" or "A / B"
  const iv = v.match(/^(.+?)\s*\.\.\s*(.+)$/) ?? v.match(/^(.+?)\s*\/\s*(.+)$/);
  if (iv) {
    return { start: iv[1].trim(), end: iv[2].trim() };
  }
  return v;
}

export function ParametersDrawer({
  params,
  onChange,
  open,
  onToggle,
}: {
  params: ParamBinding[];
  onChange: (next: ParamBinding[]) => void;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="results-drawer editor-drawer" data-testid="drawer-parameters">
      <button
        className="drawer-toggle"
        data-testid="drawer-parameters-toggle"
        onClick={onToggle}
      >
        {open ? "▾" : "▸"} Parameters {params.length > 0 ? `(${params.length})` : ""}
      </button>
      {open && (
        <div className="drawer-body">
          {params.length === 0 && (
            <p className="pane-hint" data-testid="parameters-empty">
              No parameters declared in the entrypoint library.
            </p>
          )}
          {params.map((p, i) => (
            <label key={p.name} className="param-row builder-tree-row">
              <span className="builder-caret placeholder" aria-hidden="true" />
              <span className="builder-label">{p.name}</span>
              <input
                data-testid={`param-input-${p.name}`}
                value={p.value}
                placeholder="value or start..end"
                onChange={(e) => {
                  const v = e.target.value;
                  onChange(params.map((x, j) => (j === i ? { ...x, value: v } : x)));
                }}
              />
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

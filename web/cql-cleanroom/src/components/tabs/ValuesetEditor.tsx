import { useEffect, useMemo, useState } from "react";
import { valuesetToRows } from "../../lib/valuesetBridge";

/**
 * WORKBENCH_REORG phase 3 — single-valueset editor tab. The one-vs
 * codes table (system/code/display) writes
 * back through compose.include grouping; a raw-JSON hatch preserves
 * advanced shapes. Edits commit to the workspace terminology copy.
 */

type Vs = Record<string, unknown>;
type Code = { system: string; code: string; display?: string };

function asTerminology(vs: Vs) {
  return vs as {
    url: string;
    name?: string;
    compose?: {
      include?: Array<{ system?: string; concept?: Array<{ code: string; display?: string }> }>;
    };
    expansion?: { contains?: Array<{ system?: string; code?: string; display?: string }> };
  };
}

function codesOf(vs: Vs): Code[] {
  const t = asTerminology(vs);
  const out: Code[] = [];
  for (const inc of t.compose?.include ?? []) {
    for (const c of inc.concept ?? []) {
      out.push({ system: inc.system ?? "", code: c.code, display: c.display });
    }
  }
  if (out.length) return out;
  for (const c of t.expansion?.contains ?? []) {
    if (c.code) out.push({ system: c.system ?? "", code: c.code, display: c.display });
  }
  return out;
}

function withCodes(vs: Vs, codes: Code[]): Vs {
  const t = asTerminology(vs);
  const bySystem = new Map<string, Array<{ code: string; display?: string }>>();
  for (const c of codes) {
    const list = bySystem.get(c.system) ?? [];
    list.push({ code: c.code, display: c.display });
    bySystem.set(c.system, list);
  }
  const include = [...bySystem.entries()].map(([system, concept]) => ({ system, concept }));
  return { ...vs, compose: { ...(t.compose ?? {}), include } };
}

export function ValuesetEditor({
  valueset,
  onChange,
}: {
  valueset: Vs;
  onChange: (next: Vs) => void;
}) {
  const [rawMode, setRawMode] = useState(false);
  const [rawText, setRawText] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  const codes = useMemo(() => codesOf(valueset), [valueset]);
  const warnings = useMemo(
    () => valuesetToRows([valueset]).warnings,
    [valueset],
  );
  const name = asTerminology(valueset).name;

  // Keep the raw hatch in sync while hidden (external edits flow in).
  useEffect(() => {
    if (!rawMode) setRawText(JSON.stringify(valueset, null, 2));
  }, [valueset, rawMode]);

  const setCodes = (next: Code[]) => {
    onChange(withCodes(valueset, next));
    setStatus("saved");
  };

  const patchCode = (i: number, field: keyof Code, value: string) => {
    setCodes(codes.map((c, j) => (j === i ? { ...c, [field]: value } : c)));
  };

  return (
    <section className="pane" data-testid="valueset-editor">
      <div className="pane-header">
        <div className="editor-identity">
          <span className="editor-name" data-testid="valueset-name">
            {name || "unnamed valueset"}
          </span>
          <span className="type-badge" data-testid="valueset-code-count">
            {codes.length} code{codes.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="pane-actions">
          <button
            data-testid="valueset-add-code"
            disabled={rawMode}
            onClick={() => setCodes([...codes, { system: "", code: "" }])}
          >
            + code
          </button>
          <button className="pane-action" onClick={() => setRawMode((r) => !r)}>
            {rawMode ? "table" : "raw JSON"}
          </button>
        </div>
      </div>
      {rawMode ? (
        <div className="pane-body">
          <textarea
            className="raw-json"
            data-testid="valueset-raw"
            value={rawText}
            rows={18}
            onChange={(e) => setRawText(e.target.value)}
          />
          <div className="drawer-actions">
            <button
              data-testid="valueset-raw-apply"
              onClick={() => {
                try {
                  const parsed = JSON.parse(rawText);
                  onChange(parsed);
                  setStatus("saved");
                  setRawMode(false);
                } catch (e) {
                  setStatus(e instanceof Error ? e.message : String(e));
                }
              }}
            >
              Apply
            </button>
          </div>
        </div>
      ) : (
        <div className="pane-body" data-testid="valueset-codes">
          <div className="vs-url-row">
            <label>
              url{" "}
              <input
                data-testid="valueset-url"
                value={String(asTerminology(valueset).url ?? "")}
                onChange={(e) => onChange({ ...valueset, url: e.target.value })}
              />
            </label>
          </div>
          <div className="assoc-label">Codes</div>
          {codes.length === 0 && (
            <p className="pane-hint">
              No enumerated codes (compose or expansion). Use raw JSON for
              system-wide includes.
            </p>
          )}
          {codes.map((c, i) => (
            <div className="vs-code-row" key={i}>
              <input
                aria-label="system"
                value={c.system}
                placeholder="system"
                onChange={(e) => patchCode(i, "system", e.target.value)}
              />
              <input
                aria-label="code"
                value={c.code}
                placeholder="code"
                onChange={(e) => patchCode(i, "code", e.target.value)}
              />
              <input
                aria-label="display"
                value={c.display ?? ""}
                placeholder="display"
                onChange={(e) => patchCode(i, "display", e.target.value)}
              />
              <button
                className="row-remove"
                title="remove code"
                aria-label={`remove code ${c.code || i}`}
                onClick={() => setCodes(codes.filter((_, j) => j !== i))}
              >
                ×
              </button>
            </div>
          ))}
          {warnings.length > 0 && (
            <ul className="vs-warnings">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {status && <p className="pane-meta">{status}</p>}
    </section>
  );
}

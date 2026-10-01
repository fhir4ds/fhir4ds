import { useEffect, useState } from "react";
import {
  isIntervalParam,
  joinInterval,
  splitInterval,
  toParametersResource,
  type ParamBinding,
} from "../../lib/params";

/**
 * REORG 6h — the Parameters editor: ONE shared form (values are global,
 * v7 — not per-measure). Identity row follows the valueset grammar;
 * Interval params get start/end date pickers; "export Parameters"
 * downloads the bound values as a FHIR Parameters resource.
 */

export function ParameterEditor({
  params,
  onChange,
}: {
  params: ParamBinding[];
  onChange: (next: ParamBinding[]) => void;
}) {
  const nBound = params.filter((p) => p.value.trim() !== "").length;

  // A half-bound interval isn't representable in the stored "a..b"
  // value, so the pickers compose from a per-row draft; the value is
  // written only when both halves exist (or cleared).
  const [drafts, setDrafts] = useState<
    Record<string, { start: string; end: string }>
  >({});

  // Complete intervals arriving from outside (example loads, raw edits)
  // re-sync the draft.
  useEffect(() => {
    for (const p of params) {
      if (!isIntervalParam(p)) continue;
      const halves = splitInterval(p.value);
      if (!halves) continue;
      setDrafts((d) =>
        d[p.name]?.start === halves.start && d[p.name]?.end === halves.end
          ? d
          : { ...d, [p.name]: halves },
      );
    }
  }, [params]);

  const setValue = (name: string, value: string) => {
    onChange(params.map((p) => (p.name === name ? { ...p, value } : p)));
  };

  const setIntervalHalf = (
    p: ParamBinding,
    half: "start" | "end",
    date: string,
  ) => {
    const cur = drafts[p.name] ?? { start: "", end: "" };
    const next = { ...cur, [half]: date };
    setDrafts((d) => ({ ...d, [p.name]: next }));
    setValue(p.name, joinInterval(p.type, next.start, next.end));
  };

  const downloadParameters = () => {
    const values = Object.fromEntries(params.map((p) => [p.name, p.value]));
    const blob = new Blob(
      [JSON.stringify(toParametersResource(values), null, 1)],
      { type: "application/fhir+json" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "parameters.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="pane" data-testid="parameter-editor">
      <div className="pane-header">
        <div className="editor-identity">
          <span className="editor-name">Parameters</span>
          <span className="type-badge" data-testid="param-bound-count">
            {nBound} of {params.length} bound
          </span>
        </div>
        <button
          className="pane-action"
          data-testid="param-export"
          disabled={nBound === 0}
          title="Download the bound values as a FHIR Parameters resource"
          onClick={downloadParameters}
        >
          export Parameters
        </button>
      </div>
      <div className="pane-body">
        {params.length === 0 && (
          <p className="pane-hint">
            No parameters declared in the entrypoint library.
          </p>
        )}
        {params.map((p) => {
          const interval = isIntervalParam(p);
          const halves = interval
            ? (drafts[p.name] ?? splitInterval(p.value) ?? { start: "", end: "" })
            : null;
          return (
            <div className="param-row builder-tree-row" key={p.name}>
              <span className="builder-caret placeholder" aria-hidden="true" />
              <span className="builder-label">{p.name}</span>
              {p.type && <span className="type-badge">{p.type}</span>}
              {interval ? (
                <span className="param-interval">
                  <input
                    type="date"
                    data-testid={`param-input-${p.name}`}
                    aria-label={`${p.name} start`}
                    title="interval start"
                    value={halves?.start ?? ""}
                    onChange={(e) => setIntervalHalf(p, "start", e.target.value)}
                  />
                  <input
                    type="date"
                    data-testid={`param-end-${p.name}`}
                    aria-label={`${p.name} end`}
                    title="interval end"
                    value={halves?.end ?? ""}
                    onChange={(e) => setIntervalHalf(p, "end", e.target.value)}
                  />
                </span>
              ) : (
                <input
                  data-testid={`param-input-${p.name}`}
                  value={p.value}
                  placeholder="value"
                  onChange={(e) => setValue(p.name, e.target.value)}
                />
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

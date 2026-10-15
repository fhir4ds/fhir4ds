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
  connected = false,
  umlsReady = false,
  umlsKey,
}: {
  valueset: Vs;
  onChange: (next: Vs) => void;
  /** S1R pillar 3: UMLS concept search strip (visible when connected;
   *  disabled with an explain chip when no key is available —
   *  conductor ruling 4). */
  connected?: boolean;
  umlsReady?: boolean;
  /** [2] browser-entry UMLS key (request-field doctrine; optional). */
  umlsKey?: string;
}) {
  const [rawMode, setRawMode] = useState(false);
  const [rawText, setRawText] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [umlsQuery, setUmlsQuery] = useState("");
  const [umlsBusy, setUmlsBusy] = useState(false);
  const [umlsHits, setUmlsHits] = useState<
    { system?: string; code?: string; display?: string }[] | null
  >(null);

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

  const runUmlsSearch = async () => {
    if (!umlsQuery.trim() || !umlsReady) return;
    setUmlsBusy(true);
    setUmlsHits(null);
    try {
      const res = await fetch("/api/terminology/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: umlsQuery.trim(),
          ...(umlsKey ? { api_key: umlsKey } : {}),
        }),
      });
      const body = (await res.json()) as { data?: { ok?: boolean; results?: { system?: string; code?: string; display?: string }[] } };
      const d = body?.data ?? (body as { ok?: boolean; results?: { system?: string; code?: string; display?: string }[] });
      if (d?.ok === false) {
        setStatus("UMLS search failed");
        return;
      }
      setUmlsHits(d?.results ?? []);
    } catch {
      setStatus("UMLS search failed (server unreachable)");
    } finally {
      setUmlsBusy(false);
    }
  };

  const addUmlsConcept = (hit: { system?: string; code?: string; display?: string }) => {
    const code = hit.code ?? "";
    if (!code) return;
    const next = codes.some((c) => c.code === code)
      ? codes
      : [...codes, { system: hit.system ?? "", code, display: hit.display ?? "" }];
    setCodes(next);
  };

  const patchCode = (i: number, field: keyof Code, value: string) => {
    setCodes(codes.map((c, j) => (j === i ? { ...c, [field]: value } : c)));
  };

  return (
    <section className="pane" data-testid="valueset-editor">
      {connected && (
        <div className="umls-strip" data-testid="umls-strip">
          <input
            data-testid="umls-strip-query"
            placeholder="search UMLS concepts to add…"
            value={umlsQuery}
            disabled={!umlsReady}
            onChange={(e) => setUmlsQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void runUmlsSearch();
            }}
          />
          <button
            type="button"
            data-testid="umls-strip-search"
            disabled={umlsBusy || !umlsQuery.trim() || !umlsReady}
            onClick={() => void runUmlsSearch()}
          >
            {umlsBusy ? "…" : "Search"}
          </button>
          {!umlsReady && (
            <span className="umls-strip-hint" title="browser or server key">
              add a UMLS key in Settings → Terminology to enable
            </span>
          )}
          {umlsHits && umlsHits.length > 0 && (
            <ul className="umls-strip-results" data-testid="umls-strip-results">
              {umlsHits.slice(0, 8).map((h, i) => (
                <li key={i}>
                  <button type="button" onClick={() => addUmlsConcept(h)} title="add to this valueset">
                    <code>{h.code}</code> {h.display ?? ""}{" "}
                    <span className="umls-system">{h.system}</span> +
                  </button>
                </li>
              ))}
            </ul>
          )}
          {umlsHits && umlsHits.length === 0 && (
            <span className="umls-strip-hint">no matches</span>
          )}
        </div>
      )}
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

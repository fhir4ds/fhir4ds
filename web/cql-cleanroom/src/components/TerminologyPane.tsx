import { useMemo, useState } from "react";
import { valuesetToRows } from "../lib/valuesetBridge";

/**
 * PASS2 G2: Terminology pane — ValueSet view/edit.
 *
 * Lists ValueSets from BOTH the active library's CQL declarations
 * (valueset "Name": 'url' — surfaced by parse_cql's declaration urls)
 * AND dataset valueset_resources, deduped by url with WORKSPACE
 * terminology OVERRIDING dataset sources. Provenance is displayed.
 * Codes table editor (system/code/display) edits the workspace copy;
 * a raw-JSON hatch edits compose directly (advanced shapes preserved).
 * Flatten warnings from the bridge surface inline.
 */

export interface TerminologyValueset {
  resourceType: "ValueSet";
  url: string;
  name?: string;
  compose?: {
    include?: Array<{
      system?: string;
      concept?: Array<{ code: string; display?: string }>;
    }>;
    exclude?: unknown;
  };
  expansion?: {
    contains?: Array<{ system?: string; code?: string; display?: string }>;
  } | Record<string, unknown>;
  [k: string]: unknown;
}

function isVs(v: unknown): v is TerminologyValueset {
  return (
    typeof v === "object" &&
    v !== null &&
    !Array.isArray(v) &&
    (v as Record<string, unknown>).resourceType === "ValueSet" &&
    typeof (v as Record<string, unknown>).url === "string"
  );
}

function codesOf(vs: TerminologyValueset): Array<{ system: string; code: string; display?: string }> {
  const out: Array<{ system: string; code: string; display?: string }> = [];
  // 1. Authored compose shape (VSAC "enumerated" / hand-authored).
  for (const inc of vs.compose?.include ?? []) {
    for (const c of inc.concept ?? []) {
      out.push({ system: inc.system ?? "", code: c.code, display: c.display });
    }
  }
  if (out.length) return out;
  // 2. Expansion contains (VSAC publishes many sets expansion-only;
  //    system-wide includes have no enumerated compose list).
  for (const c of (vs.expansion as { contains?: Array<{ system?: string; code?: string; display?: string }> } | undefined)?.contains ?? []) {
    if (c.code) out.push({ system: c.system ?? "", code: c.code, display: c.display });
  }
  return out;
}

function withCodes(vs: TerminologyValueset, codes: Array<{ system: string; code: string; display?: string }>): TerminologyValueset {
  // Group codes by system into compose.include entries (deterministic order).
  const bySystem = new Map<string, Array<{ code: string; display?: string }>>();
  for (const c of codes) {
    const list = bySystem.get(c.system) ?? [];
    list.push({ code: c.code, display: c.display });
    bySystem.set(c.system, list);
  }
  const include = [...bySystem.entries()].map(([system, concept]) => ({
    system,
    concept,
  }));
  const next: TerminologyValueset = { ...vs };
  next.compose = { ...vs.compose, include };
  return next;
}

export function TerminologyPane({
  cqlDeclarations,
  datasetValuesets,
  workspaceValuesets,
  onWorkspaceChange,
}: {
  /** parse_cql declarations of the ACTIVE library (kind==='valueset'). */
  cqlDeclarations: Array<Record<string, unknown>>;
  datasetValuesets: Array<Record<string, unknown>>;
  workspaceValuesets: Array<Record<string, unknown>>;
  onWorkspaceChange: (valuesets: Array<Record<string, unknown>>) => void;
}) {
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null);
  const [rawMode, setRawMode] = useState(false);
  const [rawText, setRawText] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  const declared: Array<{ name: string; url: string }> = useMemo(
    () =>
      cqlDeclarations
        .filter((d) => d.kind === "valueset" && typeof d.id === "string")
        .map((d) => ({ name: String(d.name), url: String(d.id) })),
    [cqlDeclarations],
  );

  // Union of urls: CQL declarations + dataset VS + workspace overrides.
  const urls = useMemo(() => {
    const set = new Set<string>();
    declared.forEach((d) => set.add(d.url));
    datasetValuesets.filter(isVs).forEach((v) => set.add(v.url));
    workspaceValuesets.filter(isVs).forEach((v) => set.add(v.url));
    return [...set].sort();
  }, [declared, datasetValuesets, workspaceValuesets]);

  const effective = useMemo(() => {
    const map = new Map<string, { vs: TerminologyValueset; provenance: string }>();
    for (const v of datasetValuesets.filter(isVs)) {
      map.set(v.url, { vs: v, provenance: "dataset" });
    }
    for (const v of workspaceValuesets.filter(isVs)) {
      map.set(v.url, { vs: v, provenance: "workspace" }); // override wins
    }
    return map;
  }, [datasetValuesets, workspaceValuesets]);

  const selected = selectedUrl ? effective.get(selectedUrl) ?? null : null;
  const warnings = useMemo(
    () => (selected ? valuesetToRows([selected.vs]).warnings : []),
    [selected],
  );

  const upsert = (vs: TerminologyValueset) => {
    const next = [...workspaceValuesets.filter((v) => !isVs(v) || v.url !== vs.url), vs];
    onWorkspaceChange(next);
    setStatus(`saved ${vs.url}`);
  };

  const startEdit = (vs: TerminologyValueset) => {
    setSelectedUrl(vs.url);
    setRawMode(false);
    setRawText(JSON.stringify(vs, null, 2));
  };

  const newValueset = () => {
    const url = `urn:cleanroom:vs:${Date.now().toString(36)}`;
    const vs: TerminologyValueset = {
      resourceType: "ValueSet",
      url,
      compose: { include: [] },
    };
    upsert(vs);
    startEdit(vs);
  };

  return (
    <section className="pane terminology-pane" data-testid="terminology-pane">
      <header className="pane-header">
        <h2>Terminology</h2>
        <div className="pane-actions">
          <button data-testid="terminology-add" onClick={newValueset}>
            + ValueSet
          </button>
        </div>
      </header>

      <div className="terminology-list" data-testid="terminology-list">
        {urls.length === 0 && (
          <p className="pane-hint" data-testid="terminology-empty">
            No ValueSets. Declare one in CQL (
            <code>valueset "VS": 'url'</code>) or add one here.
          </p>
        )}
        {urls.map((url) => {
          const entry = effective.get(url);
          const decl = declared.find((d) => d.url === url);
          const label = decl ? decl.name : url.split("/").pop() ?? url;
          return (
            <button
              key={url}
              className={`terminology-item ${selectedUrl === url ? "active" : ""}`}
              data-testid={`terminology-item-${url}`}
              onClick={() =>
                entry
                  ? startEdit(entry.vs)
                  : setSelectedUrl(url) /* declared but unsourced */
              }
              title={url}
            >
              <span className="terminology-name">{label}</span>
              <span className="terminology-prov">
                {decl ? "CQL " : ""}
                {entry ? entry.provenance : "unsourced"}
              </span>
              {!entry && decl ? (
                <span className="terminology-missing">no codes</span>
              ) : null}
            </button>
          );
        })}
      </div>

      {selectedUrl && !selected && (
        <p className="pane-hint" data-testid="terminology-unsourced">
          Declared in CQL but no ValueSet content loaded — add codes below
          to create a workspace override.
          <button
            data-testid="terminology-create-override"
            onClick={() => {
              const decl = declared.find((d) => d.url === selectedUrl);
              const vs: TerminologyValueset = {
                resourceType: "ValueSet",
                url: selectedUrl,
                name: decl?.name,
                compose: { include: [] },
              };
              upsert(vs);
              startEdit(vs);
            }}
          >
            create override
          </button>
        </p>
      )}

      {selected && (
        <div className="terminology-editor" data-testid="terminology-editor">
          <div className="terminology-editor-head">
            <code className="terminology-url">{selected.vs.url}</code>
            <span className="terminology-prov-badge">{selected.provenance}</span>
            <div className="pane-actions">
              <button
                data-testid="terminology-raw-toggle"
                onClick={() => setRawMode((m) => !m)}
              >
                {rawMode ? "table" : "raw JSON"}
              </button>
            </div>
          </div>

          {warnings.length > 0 && (
            <ul className="terminology-warnings" data-testid="terminology-warnings">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}

          {!rawMode && (
            <table className="terminology-table" data-testid="terminology-table">
              <thead>
                <tr>
                  <th>System</th>
                  <th>Code</th>
                  <th>Display</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {codesOf(selected.vs).map((c, i) => (
                  <tr key={i} data-testid={`terminology-code-${i}`}>
                    <td>
                      <input
                        value={c.system}
                        data-testid={`terminology-system-${i}`}
                        onChange={(e) => {
                          const codes = codesOf(selected.vs);
                          codes[i] = { ...c, system: e.target.value };
                          upsert(withCodes(selected.vs, codes));
                        }}
                      />
                    </td>
                    <td>
                      <input
                        value={c.code}
                        data-testid={`terminology-code-input-${i}`}
                        onChange={(e) => {
                          const codes = codesOf(selected.vs);
                          codes[i] = { ...c, code: e.target.value };
                          upsert(withCodes(selected.vs, codes));
                        }}
                      />
                    </td>
                    <td>
                      <input
                        value={c.display ?? ""}
                        data-testid={`terminology-display-${i}`}
                        onChange={(e) => {
                          const codes = codesOf(selected.vs);
                          codes[i] = { ...c, display: e.target.value || undefined };
                          upsert(withCodes(selected.vs, codes));
                        }}
                      />
                    </td>
                    <td>
                      <button
                        data-testid={`terminology-remove-${i}`}
                        onClick={() => {
                          const codes = codesOf(selected.vs).filter((_, idx) => idx !== i);
                          upsert(withCodes(selected.vs, codes));
                        }}
                        aria-label="remove code"
                      >
                        −
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!rawMode && (
            <button
              className="terminology-add-code"
              data-testid="terminology-add-code"
              onClick={() => {
                const codes = codesOf(selected.vs);
                codes.push({ system: "", code: "" });
                upsert(withCodes(selected.vs, codes));
              }}
            >
              + code
            </button>
          )}

          {rawMode && (
            <div className="terminology-raw">
              <textarea
                className="raw-json-editor"
                data-testid="terminology-raw-text"
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                rows={14}
                spellCheck={false}
              />
              <button
                data-testid="terminology-raw-apply"
                onClick={() => {
                  try {
                    const parsed = JSON.parse(rawText);
                    if (!isVs(parsed)) {
                      setStatus("not a ValueSet with a url");
                      return;
                    }
                    upsert(parsed);
                    setStatus(`saved ${parsed.url}`);
                    setSelectedUrl(parsed.url);
                  } catch (e) {
                    setStatus(`invalid JSON: ${e instanceof Error ? e.message : String(e)}`);
                  }
                }}
              >
                apply
              </button>
            </div>
          )}
          {status && (
            <p className="terminology-status" data-testid="terminology-status">
              {status}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

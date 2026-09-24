import { useMemo, useState } from "react";
import { workerRequest } from "./BootOverlay";
import type { FhirpathResult } from "../lib/protocol";

/**
 * C1-U7 FhirpathPane: FHIRPath playground (fhirpath_eval capability).
 *
 * Resource input is a picker over the loaded dataset, grouped by
 * resourceType (m1081 #3), with a "raw JSON" escape hatch for pasting
 * arbitrary resources. Expression → evaluated result (JSON string list);
 * errors surface as typed diagnostics from the envelope.
 */

const SAMPLE_RESOURCE = JSON.stringify(
  {
    resourceType: "Patient",
    id: "p1",
    gender: "female",
    name: [{ given: ["Ann"], family: "Abbot" }],
  },
  null,
  2,
);

export function FhirpathPane({
  dataset,
}: {
  dataset: { resources?: Array<Record<string, unknown>> } | null;
}) {
  const resources = useMemo(
    () => dataset?.resources ?? [],
    [dataset],
  );
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [resourceText, setResourceText] = useState<string | null>(null);
  const [expr, setExpr] = useState("name.given.first()");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const groups = useMemo(() => {
    const byType = new Map<string, Array<Record<string, unknown>>>();
    for (const r of resources) {
      const t = String(r.resourceType ?? "");
      if (!t) continue;
      byType.set(t, [...(byType.get(t) ?? []), r]);
    }
    return [...byType.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [resources]);

  const resourceKey = (r: Record<string, unknown>, i: number) =>
    `${r.resourceType}/${r.id ?? `#${i}`}`;

  const selectedResource = useMemo(() => {
    if (!selectedKey) return null;
    const idx = resources.findIndex((r, i) => resourceKey(r, i) === selectedKey);
    return idx >= 0 ? resources[idx] : null;
  }, [selectedKey, resources]);

  const effectiveResourceText =
    resourceText ??
    (selectedResource ? JSON.stringify(selectedResource, null, 2) : null);

  const runEval = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const resource = JSON.parse(effectiveResourceText ?? "");
      const resp = await workerRequest({
        type: "fhirpath_eval",
        path: expr,
        resource,
      });
      const env: FhirpathResult = JSON.parse(resp.envelope);
      if (!env.ok) {
        setError(env.diagnostics?.[0]?.message ?? "evaluation failed");
        return;
      }
      setResult(JSON.stringify(env.results, null, 1));
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  };

  const rawMode = resourceText !== null;

  return (
    <section className="pane fhirpath-pane" data-testid="fhirpath-pane">
      <div className="pane-header">
        <h2>FHIRPath playground</h2>
        <button
          className={rawMode ? "" : "link-btn"}
          data-testid="fp-raw-toggle"
          onClick={() => {
            setResourceText(rawMode ? null : SAMPLE_RESOURCE);
            setSelectedKey("");
          }}
        >
          {rawMode ? "Pick from dataset" : "Raw JSON"}
        </button>
      </div>
      {!rawMode ? (
        resources.length > 0 ? (
          <select
            className="fp-resource-select"
            data-testid="fp-resource-select"
            value={selectedKey}
            onChange={(e) => {
              setSelectedKey(e.target.value);
              setResult(null);
              setError(null);
            }}
            aria-label="FHIR resource"
          >
            <option value="">— select resource —</option>
            {groups.map(([type, list]) => (
              <optgroup key={type} label={`${type} (${list.length})`}>
                {list.map((r, i) => (
                  <option key={resourceKey(r, i)} value={resourceKey(r, i)}>
                    {String(r.id ?? `#${i}`)}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        ) : (
          <p className="pane-hint" data-testid="fp-no-resources">
            No dataset loaded — paste a resource via Raw JSON.
          </p>
        )
      ) : (
        <textarea
          className="fp-resource"
          data-testid="fp-resource"
          rows={8}
          value={resourceText}
          onChange={(e) => setResourceText(e.target.value)}
          spellCheck={false}
          aria-label="FHIR resource JSON"
        />
      )}
      {selectedResource && (
        <details className="fp-selected">
          <summary>selected resource</summary>
          <pre className="fp-result">{JSON.stringify(selectedResource, null, 2)}</pre>
        </details>
      )}
      <div className="fp-controls">
        <input
          className="fp-expr"
          data-testid="fp-expr"
          value={expr}
          onChange={(e) => setExpr(e.target.value)}
          placeholder="FHIRPath expression"
          aria-label="FHIRPath expression"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void runEval();
            }
          }}
        />
        <button data-testid="fp-run" onClick={runEval} disabled={running}>
          {running ? "…" : "Evaluate"}
        </button>
      </div>
      {error && (
        <div className="pane-error" data-testid="fp-error">
          {error}
        </div>
      )}
      {result !== null && (
        <pre className="fp-result" data-testid="fp-result">
          {result}
        </pre>
      )}
    </section>
  );
}

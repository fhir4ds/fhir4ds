import { useState } from "react";
import { workerRequest } from "./BootOverlay";
import type { FhirpathResult } from "../lib/protocol";

/**
 * C1-U7 FhirpathPane: FHIRPath playground (fhirpath_eval capability).
 *
 * resource JSON + expression → evaluated result (JSON string list);
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

export function FhirpathPane() {
  const [resourceText, setResourceText] = useState(SAMPLE_RESOURCE);
  const [expr, setExpr] = useState("name.given.first()");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const runEval = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const resource = JSON.parse(resourceText);
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

  return (
    <section className="pane fhirpath-pane" data-testid="fhirpath-pane">
      <div className="pane-header">
        <h2>FHIRPath playground</h2>
      </div>
      <textarea
        className="fp-resource"
        data-testid="fp-resource"
        rows={8}
        value={resourceText}
        onChange={(e) => setResourceText(e.target.value)}
        spellCheck={false}
        aria-label="FHIR resource JSON"
      />
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

import { useEffect, useCallback, useState } from "react";

/** Evidence detail for one define/column (server /api/explain payload). */
export interface ExplainEvidence {
  target?: string;
  attribute?: string | null;
  value?: string | null;
  operator?: string | null;
  threshold?: string | null;
  trace?: string[];
}

export interface ExplainDefinition {
  column: string;
  result: boolean | null;
  evidence?: ExplainEvidence[];
}

export interface ExplainPayload {
  ok: boolean;
  diagnostics?: { message: string }[];
  patient_id?: string;
  populations?: Record<string, boolean>;
  definitions?: ExplainDefinition[];
}

const POPULATION_CODES: Record<string, string> = {
  "initial population": "Initial Population",
  "denominator": "Denominator",
  "denominator exclusion": "Denominator Exclusion",
  "denominator exception": "Denominator Exception",
  "numerator": "Numerator",
  "numerator exclusion": "Numerator Exclusion",
};

function narrativeFor(def: ExplainDefinition): string[] {
  const key = def.column.trim().toLowerCase();
  const header = POPULATION_CODES[key] ?? def.column;
  const ev = def.evidence ?? [];
  if (def.result === null) {
    return [`${header}: no result for this patient.`];
  }
  if (ev.length === 0) {
    return [
      def.result
        ? `${header} is satisfied (no supporting-evidence detail was captured for this run).`
        : `${header} is not satisfied.`,
    ];
  }
  const targets = Array.from(new Set(ev.map((e) => e.target).filter(Boolean))) as string[];
  const lead = def.result
    ? `${header} is satisfied`
    : `${header} is NOT satisfied`;
  if (targets.length > 0) {
    return [`${lead} — supported by ${targets.join(", ")}.`];
  }
  return [`${lead} — ${ev.length} evidence group(s).`];
}

/**
 * Evidence modal (parity-build item 1): explains WHY each define evaluated
 * true/false for one patient, from POST /api/explain. Reuses the wasm-demo
 * EvidenceModal pattern (narrative + logic trace + evidence table).
 */
export function EvidenceModal({
  transport,
  libraries,
  library,
  patient,
  onClose,
}: {
  transport: { explain: (libs: { name: string; text: string }[], lib: string, pid: string) => Promise<ExplainPayload> };
  libraries: { name: string; text: string }[];
  library: string;
  patient: string;
  onClose: () => void;
}) {
  const [payload, setPayload] = useState<ExplainPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    transport
      .explain(libraries, library, patient)
      .then((p) => setPayload(p))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [transport, libraries, library, patient]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const defs = payload?.definitions ?? [];

  return (
    <div className="dev-evbackdrop" onClick={onClose}>
      <div className="dev-evmodal" onClick={(e) => e.stopPropagation()}>
        <div className="dev-evheader">
          <h3>
            Evidence — <span className="dev-evpatient">{patient}</span>
            <span className="dev-evlib"> · {library}</span>
          </h3>
          <button className="dev-evclose" title="Close (Esc)" onClick={onClose}>
            ✕
          </button>
        </div>
        {error && <div className="dev-vserror">{error}</div>}
        {!payload && !error && <div className="dev-evempty">Explaining…</div>}
        {payload && !payload.ok && (
          <div className="dev-vserror">
            {payload.diagnostics?.[0]?.message ?? "explain failed"}
          </div>
        )}
        {payload?.ok && defs.length === 0 && (
          <div className="dev-evempty">No definitional evidence for this patient.</div>
        )}
        {payload?.ok && defs.length > 0 && (
          <div className="dev-evbody">
            {defs.map((def) => (
              <section key={def.column} className="dev-evsection">
                <div className="dev-evsechead">
                  <span className="dev-evcol">{def.column}</span>
                  <span className={"dev-evbool " + (def.result ? "true" : "false")}>
                    {def.result === null ? "—" : def.result ? "✓ true" : "✗ false"}
                  </span>
                </div>
                <div className="dev-evnarrative">
                  {narrativeFor(def).map((line, i) => (
                    <p key={i}>{line}</p>
                  ))}
                </div>
                {(def.evidence ?? []).some((e) => (e.trace ?? []).length > 0) && (
                  <div className="dev-evtrace">
                    {(def.evidence ?? [])
                      .filter((e) => (e.trace ?? []).length > 0)
                      .map((e, i) => (
                        <div key={i} className="dev-evbreadcrumbs">
                          {(e.trace ?? []).map((step, j) => (
                            <span key={j}>
                              {j > 0 && <span className="dev-evarrow"> → </span>}
                              <span className="dev-evstep">{step}</span>
                            </span>
                          ))}
                        </div>
                      ))}
                  </div>
                )}
                {(def.evidence ?? []).length > 0 && (
                  <table className="dev-evtable">
                    <thead>
                      <tr>
                        <th>target</th>
                        <th>operator</th>
                        <th>threshold</th>
                        <th>value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(def.evidence ?? []).map((e, i) => (
                        <tr key={i} title={e.attribute ?? undefined}>
                          <td>{e.target ?? "—"}</td>
                          <td>{e.operator ?? "—"}</td>
                          <td>{e.threshold ?? "—"}</td>
                          <td>{e.value ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

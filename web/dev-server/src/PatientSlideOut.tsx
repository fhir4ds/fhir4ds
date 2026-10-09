import { useEffect, useState } from "react";
import type { HttpTransport } from "./http-transport";
import type { PatientResourceEntry, PatientResourcesResult } from "./transport";

/**
 * S5 (c-cleanroom-ux5 item 7): patient-resources slide-out — the old-wasm
 * pattern. Selecting a patient opens a right-side slide-out listing that
 * patient's resources grouped by resourceType; clicking an entry shows a
 * JSON detail view inside the slide-out.
 */
export function PatientSlideOut({
  transport,
  patient,
  onClose,
  onEditInBuilder,
}: {
  transport: HttpTransport;
  patient: string | null;
  onClose: () => void;
  onEditInBuilder?: (resource: Record<string, unknown>) => void;
}) {
  const [result, setResult] = useState<PatientResourcesResult | null>(null);
  const [detail, setDetail] = useState<PatientResourceEntry | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setResult(null);
    setDetail(null);
    setError(null);
    if (!patient) return;
    let cancelled = false;
    transport
      .patientResources(patient)
      .then((r) => {
        if (!cancelled) setResult(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [transport, patient]);

  if (!patient) return null;

  const types = Object.keys(result?.by_type ?? {}).sort();

  return (
    <div className="dev-patientslide" role="dialog" aria-label={`resources for ${patient}`}>
      <div className="dev-patientslide-head">
        <span className="dev-patientslide-title" title={patient}>
          {patient} — {result?.total ?? "…"} resources
        </span>
        <button className="dev-patientslide-close" title="Close" onClick={onClose}>
          ✕
        </button>
      </div>
      {error && <div className="dev-vserror">{error}</div>}
      {result && result.total === 0 && (
        <div className="dev-patientslide-empty">no resources for {patient}</div>
      )}
      {types.map((t) => (
        <div key={t} className="dev-patientslide-type">
          <div className="dev-patientslide-typehead">
            {t} <span className="dev-railbadge">{result?.by_type?.[t].length ?? 0}</span>
          </div>
          {(result?.by_type?.[t] ?? []).map((e) => (
            <div
              key={e.id}
              className={
                "dev-patientslide-row" + (detail?.id === e.id ? " selected" : "")
              }
              title={`${t}/${e.id}`}
              onClick={() => setDetail(e)}
            >
              <span className="dev-patientslide-rowid">{e.id}</span>
              {e.status && <span className="dev-patientslide-rowmeta">{e.status}</span>}
              {e.date && <span className="dev-patientslide-rowmeta">{String(e.date).slice(0, 10)}</span>}
            </div>
          ))}
        </div>
      ))}
      {detail && (
        <div className="dev-patientslide-detail">
          <div className="dev-patientslide-detailhead">
            <span>
              {detail.resourceType}/{detail.id}
            </span>
            <div>
              {onEditInBuilder && (
                <button
                  title="Open this resource in the builder"
                  onClick={() => {
                    try {
                      onEditInBuilder(JSON.parse(detail.preview + "…") as Record<string, unknown>);
                    } catch {
                      /* preview truncated — best effort */
                    }
                  }}
                >
                  open in builder
                </button>
              )}
              <button className="dev-patientslide-close" onClick={() => setDetail(null)}>
                ✕
              </button>
            </div>
          </div>
          <pre className="dev-patientslide-json">{detail.preview}</pre>
        </div>
      )}
    </div>
  );
}

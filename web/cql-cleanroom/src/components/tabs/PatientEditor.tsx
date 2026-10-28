import { useEffect, useMemo, useState } from "react";

/**
 * PatientEditor (S22c / AM3): one patient's data in the resource editor.
 *
 * Fetches `/api/patient/<id>` (Patient + every resource referencing
 * them, kernel-resolved), shows the resource list with type pills, and
 * edits the Patient JSON with validate + save-back to the ONE dataset
 * file (server rewrites just this patient's line; data-hint offers the
 * kernel restart — data never auto-reloads).
 */

export interface PatientBundle {
  patient_id: string;
  patient: Record<string, unknown>;
  resources: Array<Record<string, unknown>>;
  datasets?: string[];
}

export async function fetchPatient(pid: string): Promise<PatientBundle | null> {
  try {
    const res = await fetch(`/api/patient/${encodeURIComponent(pid)}`);
    if (!res.ok) return null;
    const b = (await res.json()) as { data?: PatientBundle } & PatientBundle;
    const d = b?.data ?? b;
    if (!d || !d.patient) return null;
    return d;
  } catch {
    return null;
  }
}

export async function savePatient(
  resource: Record<string, unknown>,
): Promise<{ ok: boolean; message: string }> {
  try {
    const res = await fetch("/api/patient/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resource }),
    });
    const b = (await res.json()) as {
      data?: { ok?: boolean; note?: string; diagnostics?: { message?: string }[] };
      ok?: boolean;
      note?: string;
      diagnostics?: { message?: string }[];
    };
    const d = b?.data ?? b;
    if (d?.ok === false) {
      return {
        ok: false,
        message: d?.diagnostics?.[0]?.message ?? "save failed",
      };
    }
    return { ok: true, message: d?.note ?? "saved" };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : String(e) };
  }
}

export function PatientEditor({
  patientId,
  onSaved,
}: {
  patientId: string;
  onSaved?: (pid: string) => void;
}) {
  const [bundle, setBundle] = useState<PatientBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setBundle(null);
    setError(null);
    setStatus(null);
    void fetchPatient(patientId).then((b) => {
      if (cancelled) return;
      if (!b) {
        setError(`could not load patient ${patientId}`);
        return;
      }
      setBundle(b);
      setText(JSON.stringify(b.patient, null, 2));
    });
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  const parsed = useMemo<{ ok: boolean; value?: unknown; err?: string }>(() => {
    try {
      return { ok: true, value: JSON.parse(text) };
    } catch (e) {
      return { ok: false, err: e instanceof Error ? e.message : String(e) };
    }
  }, [text]);

  const others = useMemo(
    () => (bundle?.resources ?? []).filter((r) => r !== bundle?.patient),
    [bundle],
  );

  const save = async () => {
    if (!parsed.ok || typeof parsed.value !== "object" || parsed.value === null) {
      setStatus("fix JSON errors before saving");
      return;
    }
    setBusy(true);
    const r = await savePatient(parsed.value as Record<string, unknown>);
    setBusy(false);
    setStatus(r.ok ? `saved patient ${patientId} — ${r.message}` : r.message);
    if (r.ok) onSaved?.(patientId);
  };

  return (
    <section className="pane patient-editor" data-testid="patient-editor">
      <div className="editor-identity">
        <h3>Patient {patientId}</h3>
        <span className="type-badge" data-testid="patient-resource-count">
          {bundle ? `${bundle.resources.length} resources` : "…"}
        </span>
      </div>
      {error && <p className="pane-error" data-testid="patient-error">{error}</p>}
      {bundle && (
        <>
          <div className="patient-resources" data-testid="patient-resources">
            {others.map((r, i) => (
              <span key={i} className="type-badge" title={String(r.id ?? "")}>
                {String(r.resourceType ?? "resource")}
              </span>
            ))}
          </div>
          <div className="patient-edit">
            <textarea
              className="patient-json"
              data-testid="patient-json"
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setStatus(null);
              }}
              spellCheck={false}
              rows={16}
            />
            <div className="pane-actions">
              <button
                type="button"
                className="drawer-toggle"
                data-testid="patient-validate"
                disabled={!parsed.ok}
                onClick={() =>
                  setStatus(parsed.ok ? "valid JSON" : (parsed.err ?? "invalid JSON"))
                }
              >
                Validate
              </button>
              <button
                type="button"
                className="drawer-toggle"
                data-testid="patient-save"
                disabled={!parsed.ok || busy}
                onClick={() => void save()}
              >
                {busy ? "Saving…" : "Save"}
              </button>
              {status && (
                <span className="status-note" data-testid="patient-status">
                  {status}
                </span>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

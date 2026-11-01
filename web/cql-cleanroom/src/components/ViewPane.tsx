import { useEffect, useMemo, useRef, useState } from "react";
import type { FlattenViewResult } from "../lib/protocol";
import { workerRequest } from "./BootOverlay";
import { buildDerivedView } from "../lib/viewDerivation";
import {
  jsonToVdForm,
  vdFormBlockedReasons,
  vdFormRoundTripLosses,
  vdFormToJson,
  type VdFormState,
} from "../lib/vdForm";
import { VdForm } from "./VdForm";

/**
 * ViewPane v3 — the View drawer inside Results (§3.5).
 *
 * ViewDefinitions run over the MeasureReports produced by the CQL
 * engine (evaluate → measure_report_from_rows), never raw dataset
 * resources.
 *
 * Joel (2026-10-31): ALWAYS custom — the [From Measure | Custom]
 * source switch is gone. The pane edits a ViewDefinition as JSON text
 * or, one flip away, as a guarded form. An EMPTY draft is seeded once
 * from the measure-derived VD so a fresh view tab starts runnable.
 *
 * FEATURE_VD_FORM_EDITOR presentation toggle: Form ⇄ Raw with the
 * losslessness guard (§2.2/§2.3): entering Form is BLOCKED for
 * multi-select/nested/unionAll/repeat/joins VDs and for any round-trip
 * loss; Raw is always available and the guarded flip never mutates the
 * text.
 */

export function ViewPane({
  measure,
  measureReports,
  onSql,
  onResult,
  recalcMs = 2000,
  initialVd,
  connected = false,
  onBusy,
}: {
  measure: Record<string, unknown> | null;
  measureReports: Array<Record<string, unknown>> | null;
  /** Reports the flatten SQL upward (Results Show-SQL context). */
  onSql?: (sql: string | null) => void;
  /** Reports the flatten RESULT upward — Results renders the Output pane. */
  onResult?: (r: FlattenViewResult | null) => void;
  /** REORG 6e: auto-recalc delay (settings); 0 disables auto-run. */
  recalcMs?: number;
  /** S27: a session-imported ViewDefinition (nav Views > disk VD click)
   *  — the pane boots with this text and runs it over the session
   *  MeasureReports. */
  initialVd?: Record<string, unknown> | null;
  /** S31: connected = server-side flatten (/api/view/run with explicit
   *  resources) — no in-browser engine boot. */
  connected?: boolean;
  /** S32: reports the flatten busy state upward (console output spinner). */
  onBusy?: (busy: boolean) => void;
}) {
  const [customVd, setCustomVd] = useState(
    initialVd ? JSON.stringify(initialVd, null, 2) : "",
  );
  const [error, setError] = useState<string | null>(null);

  // FEATURE_VD_FORM_EDITOR — presentation: Form ⇄ Raw (guarded).
  const [customForm, setCustomForm] = useState(false);
  const [vdForm, setVdForm] = useState<VdFormState | null>(null);
  const [flipError, setFlipError] = useState<string | null>(null);

  /** §2.6 Copy-from-Measure seeding, ALWAYS-CUSTOM edition: an empty
   * draft is seeded ONCE from the measure-derived VD (never overwrites
   * text the user typed or imported). The measure may arrive after
   * mount, so the guard waits for it; after one seed (or once the user
   * typed) it never fires again. */
  const seededRef = useRef(Boolean(initialVd));
  useEffect(() => {
    if (seededRef.current || !measure) return;
    if (customVd.trim()) {
      seededRef.current = true;
      return;
    }
    seededRef.current = true;
    setCustomVd(JSON.stringify(buildDerivedView(measure, null), null, 2));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [measure]);

  /** §2.2/§2.3 guarded flip. Raw → Form parses + runs BOTH guard layers
   * (structural block, then round-trip losses) and NEVER mutates the
   * raw text; Form → Raw seeds the text from the CURRENT form state so
   * the textarea shows exactly what the form would emit. */
  const flipPresentation = () => {
    if (!customForm) {
      try {
        const parsed = JSON.parse(customVd || "null");
        if (
          typeof parsed !== "object" ||
          parsed === null ||
          Array.isArray(parsed)
        ) {
          throw new Error("the ViewDefinition must be a JSON object");
        }
        const vd = parsed as Record<string, unknown>;
        const blocked = vdFormBlockedReasons(vd);
        if (blocked.length > 0) {
          throw new Error(
            `the form can't represent this exactly (${blocked.join("; ")}) — ` +
              "stay in Raw mode or simplify those fields",
          );
        }
        const losses = vdFormRoundTripLosses(vd);
        if (losses.length > 0) {
          throw new Error(
            `the form can't represent this exactly (${losses
              .slice(0, 4)
              .join(", ")}${losses.length > 4 ? ", …" : ""}) — ` +
              "stay in Raw mode or simplify those fields",
          );
        }
        setVdForm(jsonToVdForm(vd));
        setFlipError(null);
        setCustomForm(true);
      } catch (err) {
        setFlipError(err instanceof Error ? err.message : String(err));
      }
    } else {
      if (vdForm) {
        setCustomVd(JSON.stringify(vdFormToJson(vdForm), null, 2));
      }
      setCustomForm(false);
      setVdForm(null);
      setFlipError(null);
    }
  };

  /** Form edit → rewrite the custom VD TEXT (§2.5: the text stays the
   * single source of truth for run/flatten/history). */
  const applyVdForm = (next: VdFormState) => {
    setVdForm(next);
    setCustomVd(JSON.stringify(vdFormToJson(next), null, 2));
  };

  // U6: NO manual Run — the view recomputes after the reports or VD
  // text change (settings recalc delay; 0 = off), whenever there are
  // MeasureReports to flatten.
  const busyRef = useRef(false);
  const canAutoRun = useMemo(
    () => (measureReports?.length ?? 0) > 0 && recalcMs > 0,
    [measureReports, recalcMs],
  );
  useEffect(() => {
    if (!canAutoRun) return;
    const t = setTimeout(() => {
      if (busyRef.current) return;
      void run();
    }, recalcMs);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [measureReports, customVd, canAutoRun, recalcMs]);

  async function run() {
    busyRef.current = true;
    onBusy?.(true);
    setError(null);
    try {
      const viewDefinition = JSON.parse(customVd || "null");
      const resources = measureReports ?? [];
      // S31: CONNECTED = server-side flatten over the session reports
      // (/api/view/run accepts explicit `resources`) — no Pyodide boot on
      // the connected path. Standalone keeps the in-browser worker.
      let env: FlattenViewResult;
      if (connected) {
        const res = await fetch("/api/view/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: JSON.stringify(viewDefinition),
            resources,
          }),
        });
        const body = (await res.json()) as {
          data?: FlattenViewResult;
        } & FlattenViewResult;
        env = (body?.data ?? body) as FlattenViewResult;
      } else {
        const resp = await workerRequest({
          type: "flatten_view",
          view_definition: viewDefinition,
          resources,
        });
        env = JSON.parse((resp as { envelope: string }).envelope);
      }
      onSql?.(env.ok ? (env.sql ?? null) : null);
      onResult?.(env.ok ? env : null);
      if (!env.ok) {
        setError(env.diagnostics?.map((d) => d.message).join("; ") ?? "view failed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      onResult?.(null);
    } finally {
      busyRef.current = false;
      onBusy?.(false);
    }
  }

  return (
    <section className="pane view-pane" data-testid="view-pane">
      <header className="pane-header">
        <div className="pane-actions">
          {/* Spinner removed (Joel 2026-10-25): the results console owns
              in-flight feedback; the editor header stays quiet. */}
          {/* FEATURE_VD_FORM_EDITOR — the Form ⇄ Raw presentation switch
              (always-custom, Joel 2026-10-31): the same switch widget as
              the Builder/Cells toggles; the label names the CURRENT state
              (builder convention); aria-checked tracks FORM mode. */}
          <button
            type="button"
            className={`drawer-toggle mode-switch${customForm ? " on" : ""}`}
            data-testid="vd-presentation-toggle"
            role="switch"
            aria-label="ViewDefinition presentation (form or raw)"
            aria-checked={customForm}
            title={
              customForm
                ? "Switch to the raw JSON editor"
                : "Switch to the ViewDefinition form editor (guarded)"
            }
            onClick={flipPresentation}
          >
            {customForm ? "Form ⇄" : "Raw ⇄"}
          </button>
        </div>
      </header>
      {error && (
        <div className="pane-error" data-testid="view-error">
          {error}
        </div>
      )}
      {flipError && (
        <div className="pane-error" data-testid="vd-flip-error">
          {flipError}
        </div>
      )}
      {customForm && vdForm ? (
        <VdForm form={vdForm} onChange={applyVdForm} />
      ) : (
        <textarea
          className="vd-editor"
          data-testid="vd-editor"
          value={customVd}
          onChange={(e) => {
            setCustomVd(e.target.value);
            setFlipError(null);
          }}
          placeholder='{"resource": "Patient", "select": [...]}'
          spellCheck={false}
        />
      )}
    </section>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import type { DatasetSpec } from "../lib/protocol";
import { groupDataset, type PatientGroup } from "../lib/datasetGroup";
import { patientHint } from "./nav/PatientDetailPanel";

/**
 * WORKBENCH_REORG 6e — Tests drawer, L2 only.
 *
 * L2 "Patients": one row per patient group (`dataset-group-{pid}` on the
 * row) with a resource-count pill; clicking a row asks App to focus that
 * patient, which renders the L3 detail as a SECOND maps-style nav panel
 * (nav/PatientDetailPanel) over this one — this pane stays mounted
 * underneath, so `dataset-group-{other}` rows and the `dataset-loaded`
 * boot signal remain in the DOM while drilled in. The focused row drops
 * its `dataset-group-{pid}` testid while the detail panel owns it.
 *
 * Preserved here: `dataset-view-tree`/`dataset-view-raw` +
 * `dataset-editor` (raw NDJSON auto-commit), the L2 `dataset-filter`,
 * `dataset-add-new`, and `dataset-loaded` (mounted + visible whenever
 * the Tests panel is open — the e2e boot signal).
 */

export function DatasetPane({
  dataset,
  onDatasetChange,
  focusedPid,
  onFocusedPidChange,
  onAddForPatient,
  onAddNew,
}: {
  dataset: DatasetSpec | null;
  onDatasetChange: (ds: DatasetSpec | null) => void;
  /** Focused patient group key (null = L2 list); detail renders above. */
  focusedPid: string | null;
  onFocusedPidChange: (pid: string | null) => void;
  /** §3.2: per-patient `+` — builder opens with a Patient/<id> default. */
  onAddForPatient?: (patientId: string) => void;
  /** WORKBENCH_REORG phase 5: fresh builder tab (builder lives in a test tab now). */
  onAddNew?: () => void;
}) {
  const [text, setText] = useState(DEFAULT_NDJSON);
  const [view, setView] = useState<"tree" | "raw">("tree");
  // L2 filter: narrows the patient list (a patient row matches when its
  // id/label matches OR it owns any matching resource — so "Observation"
  // still surfaces the patients that have observations). The L3 row
  // filter lives in PatientDetailPanel.
  const [filter, setFilter] = useState("");

  const filterActive = filter.trim().length > 0;
  const matches = (r: { resourceType: string; id: string }) =>
    !filterActive ||
    r.resourceType.toLowerCase().includes(filter.trim().toLowerCase()) ||
    r.id.toLowerCase().includes(filter.trim().toLowerCase());

  const parsed = useMemo<{ resources: any[]; error: string | null }>(() => {
    if (!text.trim()) return { resources: [], error: null };
    const resources: any[] = [];
    for (const [i, line] of text.split("\n").entries()) {
      if (!line.trim()) continue;
      try {
        resources.push(JSON.parse(line));
      } catch (e) {
        return { resources: [], error: `line ${i + 1}: ${e}` };
      }
    }
    return { resources, error: null };
  }, [text]);

  const groups = useMemo(
    () => groupDataset(dataset?.resources ?? []),
    [dataset],
  );

  // AUTO-COMMIT: Raw NDJSON edits apply to the active dataset ~2s after
  // the text settles, when every line parses. Invalid text is a no-op.
  // (The Use-dataset button is hidden — kept for spec compat.)
  const lastRawCommitRef = useRef("");
  useEffect(() => {
    if (view !== "raw") return;
    if (parsed.error || parsed.resources.length === 0) return;
    const key = JSON.stringify(parsed.resources);
    const timer = setTimeout(() => {
      if (key === lastRawCommitRef.current) return;
      lastRawCommitRef.current = key;
      onDatasetChange({ resources: parsed.resources });
    }, 2000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, view]);

  // INV-C3-3: immutable replace — never mutate the dataset in place.
  const groupMatches = (g: PatientGroup) =>
    !filterActive ||
    g.key.toLowerCase().includes(filter.trim().toLowerCase()) ||
    g.label.toLowerCase().includes(filter.trim().toLowerCase()) ||
    g.rows.some(matches);

  return (
    <section className="pane" data-testid="dataset-pane">
      <header className="pane-header">
        <h2>Resources</h2>
        <span className="dataset-view-toggle">
          <button
            type="button"
            data-testid="dataset-view-tree"
            className={view === "tree" ? "active" : ""}
            onClick={() => setView("tree")}
          >
            Tree
          </button>
          <button
            type="button"
            data-testid="dataset-view-raw"
            className={view === "raw" ? "active" : ""}
            onClick={() => setView("raw")}
          >
            Raw
          </button>
        </span>
        <button
          data-testid="load-dataset"
          hidden
          disabled={!!parsed.error || !parsed.resources.length}
          onClick={() => onDatasetChange({ resources: parsed.resources })}
        >
          Use dataset ({parsed.resources.length})
        </button>
      </header>
      {view === "raw" && (
        <>
          {parsed.error && (
            <div className="pane-error" data-testid="dataset-error">
              {parsed.error}
            </div>
          )}
          <textarea
            className="dataset-editor"
            data-testid="dataset-editor"
            value={text}
            onChange={(e) => setText(e.target.value)}
            spellCheck={false}
          />
        </>
      )}
      {dataset && (
        <div className="dataset-loaded" data-testid="dataset-loaded">
          Active: {dataset.resources?.length ?? 0} resources
        </div>
      )}
      {view === "tree" && dataset && (dataset.resources?.length ?? 0) > 0 && (
        <>
          {!focusedPid && (
            <div className="dataset-tree-controls">
              <input
                data-testid="dataset-filter"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="filter by type or id"
                aria-label="filter dataset"
              />
              {onAddNew && (
                <button
                  type="button"
                  data-testid="dataset-add-new"
                  onClick={onAddNew}
                  title="Open a new-resource builder tab"
                >
                  + New
                </button>
              )}
            </div>
          )}
          <div className="dataset-tree" data-testid="dataset-tree">
            {groups
              .filter(groupMatches)
              .map((g) => (
                <PatientRow
                  key={g.key}
                  group={g}
                  focused={focusedPid === g.key}
                  onDrillIn={() => onFocusedPidChange(g.key)}
                  onAddForPatient={onAddForPatient}
                />
              ))}
          </div>
        </>
      )}
      {view === "tree" && dataset && !groups.some((g) => !g.unattributed) && (
        <div className="pane-empty" data-testid="dataset-no-patients">
          No patient-attributed resources — patient-context evaluation will
          see none of these.
        </div>
      )}
    </section>
  );
}

/**
 * L2 — one maps-style row per patient group. Click = drill in (the L3
 * detail slides out as a second nav panel); the `+` button adds a
 * resource for the patient WITHOUT drilling. While THIS patient's
 * detail panel is up, the row drops its `dataset-group-{pid}` testid
 * (the detail owns it) and its `+` (unreachable under the overlay).
 */
function PatientRow({
  group,
  focused,
  onDrillIn,
  onAddForPatient,
}: {
  group: PatientGroup;
  focused: boolean;
  onDrillIn: () => void;
  onAddForPatient?: (patientId: string) => void;
}) {
  const patientRow = group.rows.find((r) => r.resourceType === "Patient");
  const hint = patientRow
    ? patientHint(patientRow.resource)
    : group.unattributed
      ? null
      : group.phantom
        ? "resources reference this uuid, but no Patient with that id exists"
        : "no Patient resource with this id";
  return (
    <div
      className="dataset-patient-row"
      data-testid={focused ? undefined : `dataset-group-${group.key}`}
      data-phantom={group.phantom ? "true" : undefined}
      data-unattributed={group.unattributed ? "true" : undefined}
      onClick={onDrillIn}
      title={`Show ${group.key}'s resources`}
    >
      <span className="dataset-caret" aria-hidden="true">
        ▸
      </span>
      <span
        className={`dataset-group-label${group.unattributed ? " muted" : ""}${group.phantom ? " phantom" : ""}`}
      >
        {group.unattributed ? "Unattributed" : group.label}
        {hint && (
          <span className="dataset-group-hint" title={hint}>
            {" "}
            — {hint}
          </span>
        )}
      </span>
      {group.phantom && (
        <span
          className="dataset-group-hint"
          title="Add the Patient with this id first, then author resources for it"
        >
          add Patient/{group.key} first
        </span>
      )}
      <span className="dataset-count-pill">{group.rows.length}</span>
      {!focused && !group.unattributed && !group.phantom && onAddForPatient && (
        <button
          type="button"
          className="dataset-add-btn"
          data-testid={`dataset-add-${group.key}`}
          onClick={(e) => {
            e.stopPropagation(); // the row drills in — the + must ADD.
            onAddForPatient(group.key);
          }}
          title={`New resource for ${group.label} (subject defaults to Patient/${group.key})`}
        >
          +
        </button>
      )}
    </div>
  );
}

const DEFAULT_NDJSON = [
  JSON.stringify({ resourceType: "Patient", id: "p1", gender: "female", name: [{ given: ["Ann"] }] }),
  JSON.stringify({ resourceType: "Patient", id: "p2", gender: "male", name: [{ given: ["Bob"] }] }),
  JSON.stringify({ resourceType: "Patient", id: "p3", gender: "female" }),
].join("\n");

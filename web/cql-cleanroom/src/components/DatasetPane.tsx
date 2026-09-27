import { useMemo, useState } from "react";
import type { DatasetSpec } from "../lib/protocol";
import { groupDataset, type PatientGroup } from "../lib/datasetGroup";
import { patientHint } from "./nav/PatientDetailPanel";

/**
 * REORG 6f.1 — Tests drawer, L2 only, no chrome: the patient list fills
 * the nav panel (one row per patient group with a count pill); the L3
 * detail (nav/PatientDetailPanel) slides out BESIDE it while a patient
 * is focused. The focused row drops its `dataset-group-{pid}` testid
 * while the detail panel owns it, so `dataset-group-{other}` rows stay
 * addressable while drilled in.
 *
 * Kept content signals: the L2 `dataset-filter`, `dataset-add-new`, and
 * `dataset-tree` (+ `dataset-group-*` rows) — what the e2e suite waits on.
 */

export function DatasetPane({
  dataset,
  focusedPid,
  onFocusedPidChange,
  onAddForPatient,
  onAddNew,
}: {
  dataset: DatasetSpec | null;
  /** Focused patient group key (null = L2 list); detail renders beside. */
  focusedPid: string | null;
  onFocusedPidChange: (pid: string | null) => void;
  /** §3.2: per-patient `+` — builder opens with a Patient/<id> default. */
  onAddForPatient?: (patientId: string) => void;
  /** WORKBENCH_REORG phase 5: fresh builder tab (builder lives in a test tab now). */
  onAddNew?: () => void;
}) {
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

  const groups = useMemo(
    () => groupDataset(dataset?.resources ?? []),
    [dataset],
  );

  // INV-C3-3: immutable replace — never mutate the dataset in place.
  const groupMatches = (g: PatientGroup) =>
    !filterActive ||
    g.key.toLowerCase().includes(filter.trim().toLowerCase()) ||
    g.label.toLowerCase().includes(filter.trim().toLowerCase()) ||
    g.rows.some(matches);

  return (
    <section className="dataset-pane" data-testid="dataset-pane">
      {dataset && (dataset.resources?.length ?? 0) > 0 && (
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
      {dataset && !groups.some((g) => !g.unattributed) && (
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

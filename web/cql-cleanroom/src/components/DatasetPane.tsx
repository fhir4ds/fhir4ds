import { useMemo } from "react";
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
 * REORG 6h — the filter and the add (`+`) live in the section HEADER
 * (DrawerSection, like every other nav section); this pane renders the
 * list only.
 */

export function DatasetPane({
  dataset,
  focusedPid,
  onFocusedPidChange,
  filter,
}: {
  dataset: DatasetSpec | null;
  /** Focused patient group key (null = L2 list); detail renders beside. */
  focusedPid: string | null;
  onFocusedPidChange: (pid: string | null) => void;
  /** Section-header filter (a row matches when its id/label matches OR
   *  it owns any matching resource — "Observation" still surfaces the
   *  patients that have observations). */
  filter: string;
}) {
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
        <div className="dataset-tree" data-testid="dataset-tree">
          {groups
            .filter(groupMatches)
            .map((g) => (
              <PatientRow
                key={g.key}
                group={g}
                focused={focusedPid === g.key}
                onDrillIn={() => onFocusedPidChange(g.key)}
              />
            ))}
        </div>
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
 * detail slides out as a second nav panel; per-patient add lives in the
 * detail's per-type groups). While THIS patient's detail panel is up,
 * the row drops its `dataset-group-{pid}` testid (the detail owns it).
 */
function PatientRow({
  group,
  focused,
  onDrillIn,
}: {
  group: PatientGroup;
  focused: boolean;
  onDrillIn: () => void;
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
    </div>
  );
}

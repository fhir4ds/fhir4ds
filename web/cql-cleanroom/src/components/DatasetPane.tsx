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
 * S25: CONNECTED mode feeds the SAME L2/L3 UX from local files — roster
 * rows (id + resource-count chip) come from the server workspace, and a
 * click drills into the SAME right-side detail panel (App resolves the
 * group from the server roster). Standalone is unchanged. The old
 * "Live dataset:" banner is gone — the roster itself is the statement.
 */

export interface ServerPatientEntry {
  id: string;
  count: number;
  types: Record<string, number>;
}

export function DatasetPane({
  dataset,
  focusedPid,
  onFocusedPidChange,
  filter,
  serverPatientIds,
  serverPatientResources,
}: {
  dataset: DatasetSpec | null;
  /** Connected roster (S22a: authoritative even when EMPTY; null = standalone). */
  serverPatientIds?: string[] | null;
  /** S24-3: per-patient resource counts + type breakdown (server mode). */
  serverPatientResources?: ServerPatientEntry[] | null;
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

  const countById = useMemo(() => {
    const m = new Map<string, ServerPatientEntry>();
    for (const e of serverPatientResources ?? []) m.set(e.id, e);
    return m;
  }, [serverPatientResources]);

  const serverRowMatches = (pid: string) => {
    if (!filterActive) return true;
    const q = filter.trim().toLowerCase();
    if (pid.toLowerCase().includes(q)) return true;
    const entry = countById.get(pid);
    if (!entry) return false;
    return Object.entries(entry.types).some(
      ([type, n]) => type.toLowerCase().includes(q) || String(n) === q,
    );
  };

  // INV-C3-3: immutable replace — never mutate the dataset in place.
  const groupMatches = (g: PatientGroup) =>
    !filterActive ||
    g.key.toLowerCase().includes(filter.trim().toLowerCase()) ||
    g.label.toLowerCase().includes(filter.trim().toLowerCase()) ||
    g.rows.some(matches);

  return (
    <section className="dataset-pane" data-testid="dataset-pane">
      {serverPatientIds && serverPatientIds.length > 0 && (
        <div className="dataset-tree" data-testid="ds-server-roster">
          {serverPatientIds
            .filter(serverRowMatches)
            .slice(0, 50)
            .map((pid) => (
              <ServerPatientRow
                key={pid}
                pid={pid}
                count={countById.get(pid)?.count}
                focused={focusedPid === pid}
                onDrillIn={() => onFocusedPidChange(pid)}
              />
            ))}
          {serverPatientIds.length > 50 && (
            <div className="ds-roster-row">+ {serverPatientIds.length - 50} more…</div>
          )}
        </div>
      )}
      {serverPatientIds && serverPatientIds.length === 0 && (
        <div className="pane-hint" data-testid="dataset-empty-server" role="status" style={{ padding: "6px 10px" }}>
          Live dataset: server workspace (0 patients) — add patient data under
          the workspace's data directory, then restart the kernel.
        </div>
      )}
      {serverPatientIds ? null : (
        dataset &&
        (dataset.resources?.length ?? 0) > 0 && (
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
        )
      )}
      {(!serverPatientIds || serverPatientIds.length === 0) &&
        !serverPatientIds &&
        dataset &&
        !groups.some((g) => !g.unattributed) && (
          <div className="pane-empty" data-testid="dataset-no-patients">
            No patient-attributed resources — patient-context evaluation will
            see none of these.
          </div>
        )}
    </section>
  );
}

/**
 * Connected L2 row — one per SERVER patient: the id plus a
 * resource-count chip. Click drills into the SAME right-side L3 detail
 * panel as standalone (App resolves the group from the server roster).
 */
function ServerPatientRow({
  pid,
  count,
  focused,
  onDrillIn,
}: {
  pid: string;
  count?: number;
  focused: boolean;
  onDrillIn: () => void;
}) {
  return (
    <div
      className="dataset-patient-row ds-roster-row"
      data-testid={focused ? undefined : "ds-roster-row"}
      data-pid={pid}
      role="button"
      tabIndex={0}
      onClick={onDrillIn}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onDrillIn();
      }}
      title={`Show ${pid}'s resources`}
    >
      <span className="dataset-group-label">{pid}</span>
      {typeof count === "number" && (
        <span className="dataset-count-pill" data-testid="ds-roster-count">
          {count}
        </span>
      )}
    </div>
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

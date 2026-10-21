import { useEffect, useMemo, useState } from "react";
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
 *
 * S24-3 (published-docs UX): connected mode lists patients BY ID, each
 * with a chip showing that patient's RESOURCE COUNT; clicking a patient
 * opens an in-pane slideout listing their resources grouped BY TYPE
 * (fetched from /api/patient/resources). The old "Live dataset:"
 * banner is gone — the patient-list UX itself carries the meaning.
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
  onOpenPatient,
}: {
  dataset: DatasetSpec | null;
  /** Connected roster (S22a: authoritative even when EMPTY; null = standalone). */
  serverPatientIds?: string[] | null;
  /** S24-3: per-patient resource counts + type breakdown (server mode). */
  serverPatientResources?: ServerPatientEntry[] | null;
  /** S22c: open this patient's data in the resource editor (connected). */
  onOpenPatient?: (pid: string) => void;
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

  // S24-3: connected slideout state (resources by type for one patient).
  const [slideout, setSlideout] = useState<{
    pid: string;
    byType: Record<string, Array<{ id: string; status?: string; date?: string }>>;
  } | null>(null);
  const [slideoutLoading, setSlideoutLoading] = useState(false);

  useEffect(() => {
    // Close the slideout when the roster changes out from under it.
    if (slideout && serverPatientIds && !serverPatientIds.includes(slideout.pid)) {
      setSlideout(null);
    }
  }, [serverPatientIds, slideout]);

  const openSlideout = async (pid: string) => {
    setSlideoutLoading(true);
    try {
      const res = await fetch(
        `/api/patient/resources?id=${encodeURIComponent(pid)}`,
      );
      const b = (await res.json()) as {
        by_type?: Record<string, Array<Record<string, unknown>>>;
      };
      const raw = b?.by_type ?? {};
      const byType: Record<
        string,
        Array<{ id: string; status?: string; date?: string }>
      > = {};
      for (const [type, list] of Object.entries(raw)) {
        byType[type] = (list ?? []).map((r) => ({
          id: String(r.id ?? ""),
          status: typeof r.status === "string" ? r.status : undefined,
          date:
            typeof r.effectiveDateTime === "string"
              ? r.effectiveDateTime
              : typeof r.effectiveDate === "string"
                ? r.effectiveDate
                : typeof r.authoredOn === "string"
                  ? r.authoredOn
                  : typeof r.birthDate === "string"
                    ? r.birthDate
                    : undefined,
        }));
      }
      setSlideout({ pid, byType });
    } catch {
      setSlideout(null);
    } finally {
      setSlideoutLoading(false);
    }
  };

  const countById = useMemo(() => {
    const m = new Map<string, ServerPatientEntry>();
    for (const e of serverPatientResources ?? []) m.set(e.id, e);
    return m;
  }, [serverPatientResources]);

  return (
    <section className="dataset-pane" data-testid="dataset-pane">
      {serverPatientIds && serverPatientIds.length > 0 && (
        <div className="ds-server-roster" data-testid="ds-server-roster">
          {serverPatientIds.slice(0, 50).map((pid) => {
            const entry = countById.get(pid);
            const active = slideout?.pid === pid;
            return (
              <div
                key={pid}
                className={`ds-roster-row ds-roster-row-editable${active ? " active" : ""}`}
                data-testid="ds-roster-row"
                role="button"
                tabIndex={0}
                aria-pressed={active}
                title={`${entry?.count ?? 0} resources — click to list by type, double-click to edit in the resource editor`}
                onClick={() => void openSlideout(pid)}
                onDoubleClick={() => onOpenPatient?.(pid)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    void openSlideout(pid);
                  }
                }}
              >
                <span className="ds-roster-id">{pid}</span>
                <span className="dataset-count-pill" data-testid="ds-roster-count">
                  {entry?.count ?? 0}
                </span>
              </div>
            );
          })}
          {serverPatientIds.length > 50 && (
            <div className="ds-roster-row">+ {serverPatientIds.length - 50} more…</div>
          )}
        </div>
      )}
      {serverPatientIds && serverPatientIds.length === 0 && (
        <div className="pane-hint" data-testid="dataset-empty-server" role="status" style={{ padding: "6px 10px" }}>
          No patients in the server workspace — add patient data under the
          workspace's Patient folders, then restart the kernel.
        </div>
      )}
      {slideoutLoading && (
        <div className="pane-hint" data-testid="ds-slideout-loading" role="status">
          loading {slideout?.pid ?? ""}…
        </div>
      )}
      {slideout && !slideoutLoading && (
        <div
          className="ds-patient-slideout"
          data-testid="ds-patient-slideout"
          aria-label={`Resources for ${slideout.pid} by type`}
        >
          <div className="ds-slideout-head">
            <strong>Patient {slideout.pid}</strong>
            <button
              type="button"
              className="settings-button"
              data-testid="ds-slideout-close"
              onClick={() => setSlideout(null)}
              aria-label="Close patient resources"
            >
              ×
            </button>
          </div>
          {Object.keys(slideout.byType).length === 0 && (
            <div className="pane-hint">no resources</div>
          )}
          {Object.entries(slideout.byType)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([type, list]) => (
              <div key={type} className="ds-slideout-type" data-testid="ds-slideout-type">
                <div className="ds-slideout-type-head">
                  <span className="type-badge">{type}</span>
                  <span className="dataset-count-pill">{list.length}</span>
                </div>
                <ul className="ds-slideout-list">
                  {list.map((r) => (
                    <li
                      key={r.id}
                      className="ds-slideout-resource"
                      data-testid="ds-slideout-resource"
                      title={r.id}
                    >
                      {r.id}
                      {r.date && <span className="ds-slideout-date"> {r.date}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          <button
            type="button"
            className="settings-button"
            data-testid="ds-slideout-edit"
            onClick={() => onOpenPatient?.(slideout.pid)}
          >
            Edit patient data…
          </button>
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

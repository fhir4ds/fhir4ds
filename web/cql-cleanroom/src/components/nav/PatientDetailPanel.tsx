import { useState } from "react";
import {
  attributionWhy,
  type DatasetRowRef,
  type PatientGroup,
} from "../../lib/datasetGroup";

/**
 * REORG 6e — the Tests L3 patient detail, now a SECOND maps-style nav
 * panel: App renders it into NavRail's `detailSlot` overlay while a
 * patient is focused, so the L2 patient list stays mounted underneath
 * (`dataset-group-{other}` rows remain in the DOM).
 *
 * It keeps the old L3 surface verbatim: `dataset-back`, per-patient `+`
 * (`dataset-add-{pid}`), the `dataset-filter` input (this panel owns it
 * while drilled in), Expand/Collapse all, and per-type groups with
 * `dataset-type-toggle-{pid}-{Type}`, capped `dataset-row-{index}` rows
 * and `dataset-more-{pid}-{Type}`.
 *
 * The wrapper keeps `data-testid=dataset-group-{pid}` (specs assert its
 * textContent at L3); the L2 PatientRow drops its duplicate while this
 * patient is focused. Filter/collapse state is local: drilling out and
 * back in resets the view.
 */

const TYPE_ROW_CAP = 25;

function groupTypes(group: PatientGroup): string[] {
  return [...new Set(group.rows.map((r) => r.resourceType))].sort();
}

export function patientHint(resource: Record<string, unknown>): string | null {
  const parts: string[] = [];
  if (typeof resource.gender === "string") parts.push(resource.gender);
  const name = Array.isArray(resource.name)
    ? (resource.name[0] as Record<string, unknown> | undefined)
    : undefined;
  if (name && Array.isArray(name.given) && typeof name.given[0] === "string") {
    parts.push(String(name.given[0]));
  } else if (
    name &&
    typeof name.family === "string" &&
    !name.given
  ) {
    parts.push(name.family);
  }
  return parts.length ? parts.join(", ") : null;
}

export function PatientDetailPanel({
  group,
  onBack,
  onEditResource,
  onAddForPatient,
  onAddNew,
  onDelete,
}: {
  group: PatientGroup;
  onBack: () => void;
  /** C3-U3: asks the builder to prefill from the row at STORAGE index i. */
  onEditResource?: (index: number) => void;
  /** §3.2: per-patient `+` — builder opens with a Patient/<id> default. */
  onAddForPatient?: (patientId: string) => void;
  onAddNew?: () => void;
  onDelete: (index: number) => void;
}) {
  const [filter, setFilter] = useState("");
  const [collapsedTypes, setCollapsedTypes] = useState<Set<string>>(new Set());
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());
  const [uncappedTypes, setUncappedTypes] = useState<Set<string>>(new Set());

  const filterActive = filter.trim().length > 0;
  const matches = (r: { resourceType: string; id: string }) =>
    !filterActive ||
    r.resourceType.toLowerCase().includes(filter.trim().toLowerCase()) ||
    r.id.toLowerCase().includes(filter.trim().toLowerCase());
  const typeKey = (groupKey: string, type: string) => `${groupKey}::${type}`;

  const collapseAll = () => {
    const all = new Set<string>();
    for (const t of groupTypes(group)) all.add(typeKey(group.key, t));
    setCollapsedTypes(all);
  };

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
      className="dataset-patient-detail dataset-group"
      data-testid={`dataset-group-${group.key}`}
      data-phantom={group.phantom ? "true" : undefined}
      data-unattributed={group.unattributed ? "true" : undefined}
    >
      <div className="dataset-detail-head">
        <button
          type="button"
          className="dataset-back"
          data-testid="dataset-back"
          onClick={onBack}
          title="Back to the patient list"
        >
          ‹ Patients
        </button>
        <span
          className={`dataset-group-label${group.unattributed ? " muted" : ""}${group.phantom ? " phantom" : ""}`}
        >
          {group.unattributed ? "Unattributed" : group.label}
          {" "}
          <span className="dataset-count-pill">{group.rows.length}</span>
        </span>
        {hint && (
          <span className="dataset-group-hint" title={hint}>
            — {hint}
          </span>
        )}
        {!group.unattributed && !group.phantom && onAddForPatient && (
          <button
            type="button"
            className="dataset-add-btn"
            data-testid={`dataset-add-${group.key}`}
            onClick={() => onAddForPatient(group.key)}
            title={`New resource for ${group.label} (subject defaults to Patient/${group.key})`}
          >
            +
          </button>
        )}
        {group.phantom && (
          <span
            className="dataset-group-hint"
            title="Add the Patient with this id first, then author resources for it"
          >
            add Patient/{group.key} first
          </span>
        )}
      </div>
      <div className="dataset-tree-controls">
        <input
          data-testid="dataset-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="filter by type or id"
          aria-label="filter dataset"
        />
        <button
          type="button"
          data-testid="dataset-expand-all"
          onClick={() => setCollapsedTypes(new Set())}
        >
          Expand all
        </button>
        <button
          type="button"
          data-testid="dataset-collapse-all"
          onClick={collapseAll}
        >
          Collapse all
        </button>
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
      {groupTypes(group).map((type) => (
        <TypeGroup
          key={type}
          groupKey={group.key}
          unattributed={group.unattributed}
          type={type}
          rows={group.rows.filter((r) => r.resourceType === type)}
          filter={filter}
          matches={matches}
          collapsedTypes={collapsedTypes}
          setCollapsedTypes={setCollapsedTypes}
          expandedTypes={expandedTypes}
          setExpandedTypes={setExpandedTypes}
          uncappedTypes={uncappedTypes}
          setUncappedTypes={setUncappedTypes}
          onEditResource={onEditResource}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}

/**
 * One resource-type group inside L3 — extracted verbatim from the old
 * inline PatientGroupNode body. OQ-1 RESOLVED semantics kept: type
 * groups default COLLAPSED with a count pill; filter active →
 * auto-expand + bypass the row cap (gemini C: matches never hide).
 */
function TypeGroup({
  groupKey,
  unattributed,
  type,
  rows,
  filter,
  matches,
  collapsedTypes,
  setCollapsedTypes,
  expandedTypes,
  setExpandedTypes,
  uncappedTypes,
  setUncappedTypes,
  onEditResource,
  onDelete,
}: {
  groupKey: string;
  unattributed: boolean;
  type: string;
  rows: DatasetRowRef[];
  filter: string;
  matches: (r: { resourceType: string; id: string }) => boolean;
  collapsedTypes: Set<string>;
  setCollapsedTypes: (s: Set<string>) => void;
  expandedTypes: Set<string>;
  setExpandedTypes: (s: Set<string>) => void;
  uncappedTypes: Set<string>;
  setUncappedTypes: (s: Set<string>) => void;
  onEditResource?: (index: number) => void;
  onDelete: (index: number) => void;
}) {
  const filterActive = filter.trim().length > 0;
  const key = `${groupKey}::${type}`;
  // Default COLLAPSED: every type group starts closed (filter
  // auto-expands; user toggles win). capBypassed = show-more
  // lifted the 25-row cap for THIS group.
  const userCollapsed = collapsedTypes.has(key);
  const userExpanded = expandedTypes.has(key);
  const uncapped = uncappedTypes.has(key);
  const isOpen = filterActive
    ? true
    : userCollapsed
      ? false // explicit collapse wins (re-open clears the flag now)
      : userExpanded;
  const capBypassed = filterActive || uncapped;
  const candidates = filterActive ? rows.filter(matches) : rows;
  const visible = isOpen
    ? capBypassed
      ? candidates
      : candidates.slice(0, TYPE_ROW_CAP)
    : [];
  const hidden = candidates.length - visible.length;
  return (
    <div className="dataset-type-group" data-testid={`dataset-type-${groupKey}-${type}`}>
      <button
        type="button"
        className="dataset-type-toggle"
        data-testid={`dataset-type-toggle-${groupKey}-${type}`}
        onClick={() => {
          // Symmetric toggle: OPEN clears the collapsed flag AND
          // sets expand (big groups render capped + show-more);
          // COLLAPSE clears expand AND sets collapsed.
          if (!isOpen) {
            const ex = new Set(expandedTypes);
            ex.add(key);
            setExpandedTypes(ex);
            const cx = new Set(collapsedTypes);
            cx.delete(key);
            if (cx.size !== collapsedTypes.size) setCollapsedTypes(cx);
          } else {
            const cx = new Set(collapsedTypes);
            cx.add(key);
            setCollapsedTypes(cx);
            const ex = new Set(expandedTypes);
            ex.delete(key);
            if (ex.size !== expandedTypes.size) setExpandedTypes(ex);
          }
        }}
      >
        <span className="dataset-caret">{isOpen ? "▾" : "▸"}</span>
        <span className="dataset-type-name">{type}</span>
        <span className="dataset-count-pill">{rows.length}</span>
      </button>
      {isOpen &&
        visible.map((r) => (
          <div
            key={r.index}
            className="dataset-row"
            data-testid={`dataset-row-${r.index}`}
            onClick={() => onEditResource?.(r.index)}
            title="Edit in Resource Builder"
          >
            <span className="dataset-row-id">
              {r.resourceType}/{r.id}
              {unattributed && (
                <span
                  className="dataset-why"
                  data-testid={`dataset-why-${r.index}`}
                  title={attributionWhy(r.resource)}
                >
                  ?
                </span>
              )}
            </span>
            <span className="dataset-row-actions">
              <button
                type="button"
                data-testid={`dataset-edit-${r.index}`}
                onClick={(e) => {
                  e.stopPropagation(); // the row already opens the builder.
                  onEditResource?.(r.index);
                }}
                title="Edit in Resource Builder"
              >
                Edit
              </button>
              <button
                type="button"
                data-testid={`dataset-delete-${r.index}`}
                onClick={(e) => {
                  e.stopPropagation(); // a row click must not pre-empt delete.
                  onDelete(r.index);
                }}
                title="Remove from dataset"
              >
                ×
              </button>
            </span>
          </div>
        ))}
      {!filterActive && isOpen && hidden > 0 && (
        <button
          type="button"
          className="dataset-more"
          data-testid={`dataset-more-${groupKey}-${type}`}
          onClick={() => {
            const ex = new Set(uncappedTypes);
            ex.add(key);
            setUncappedTypes(ex);
          }}
        >
          + show {hidden} more
        </button>
      )}
    </div>
  );
}

import { useMemo, useState } from "react";
import type { DatasetSpec } from "../lib/protocol";
import {
  attributionWhy,
  groupDataset,
  type PatientGroup,
} from "../lib/datasetGroup";

export function DatasetPane({
  dataset,
  onDatasetChange,
  onEditResource,
  onAddForPatient,
}: {
  dataset: DatasetSpec | null;
  onDatasetChange: (ds: DatasetSpec | null) => void;
  /** C3-U3: asks the builder to prefill from the row at STORAGE index i. */
  onEditResource?: (index: number) => void;
  /** §3.2: per-patient `+` — builder opens with a Patient/<id> default. */
  onAddForPatient?: (patientId: string) => void;
}) {
  const [text, setText] = useState(DEFAULT_NDJSON);
  const [view, setView] = useState<"tree" | "raw">("tree");
  // WORKBENCH_REORG §3.4 — scale controls.
  const [filter, setFilter] = useState("");
  const [collapsedTypes, setCollapsedTypes] = useState<Set<string>>(new Set());
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());
  const [uncappedTypes, setUncappedTypes] = useState<Set<string>>(new Set());
  const TYPE_ROW_CAP = 25;

  const filterActive = filter.trim().length > 0;
  const matches = (r: { resourceType: string; id: string }) =>
    !filterActive ||
    r.resourceType.toLowerCase().includes(filter.trim().toLowerCase()) ||
    r.id.toLowerCase().includes(filter.trim().toLowerCase());

  const typeKey = (groupKey: string, type: string) => `${groupKey}::${type}`;

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

  return (
    <section className="pane" data-testid="dataset-pane">
      <header className="pane-header">
        <h2>Dataset</h2>
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
              onClick={() => {
                const all = new Set<string>();
                for (const g of groups) {
                  for (const t of groupTypes(g)) all.add(typeKey(g.key, t));
                }
                setCollapsedTypes(all);
              }}
            >
              Collapse all
            </button>
          </div>
          <div className="dataset-tree" data-testid="dataset-tree">
            {groups
              .map((g) => ({ g, rows: g.rows.filter(matches) }))
              .filter(({ rows }) => rows.length > 0 || (!filterActive && true))
              .filter(({ g, rows }) =>
                filterActive ? rows.length > 0 : !g.unattributed || g.rows.length > 0,
              )
              .map(({ g }) => (
                <PatientGroupNode
                  key={g.key}
                  group={g}
                  filter={filter}
                  matches={matches}
                  collapsedTypes={collapsedTypes}
                  setCollapsedTypes={setCollapsedTypes}
                  expandedTypes={expandedTypes}
                  uncappedTypes={uncappedTypes}
                  setUncappedTypes={setUncappedTypes}
                  setExpandedTypes={setExpandedTypes}
                  typeRowCap={TYPE_ROW_CAP}
                  onEditResource={onEditResource}
                  onAddForPatient={onAddForPatient}
                  onDelete={(i) => {
                    // Immutable replace (INV-C3-3): never mutate in place.
                    const resources = (dataset.resources ?? []).filter(
                      (_, j) => j !== i,
                    );
                    onDatasetChange({ ...dataset, resources });
                  }}
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

function groupTypes(group: PatientGroup): string[] {
  return [...new Set(group.rows.map((r) => r.resourceType))].sort();
}

function PatientGroupNode({
  group,
  filter,
  matches,
  collapsedTypes,
  setCollapsedTypes,
  expandedTypes,
  setExpandedTypes,
  uncappedTypes,
  setUncappedTypes,
  typeRowCap,
  onEditResource,
  onAddForPatient,
  onDelete,
}: {
  group: PatientGroup;
  filter: string;
  matches: (r: { resourceType: string; id: string }) => boolean;
  collapsedTypes: Set<string>;
  setCollapsedTypes: (s: Set<string>) => void;
  expandedTypes: Set<string>;
  setExpandedTypes: (s: Set<string>) => void;
  uncappedTypes: Set<string>;
  setUncappedTypes: (s: Set<string>) => void;
  typeRowCap: number;
  onEditResource?: (index: number) => void;
  onAddForPatient?: (patientId: string) => void;
  onDelete: (index: number) => void;
}) {
  const filterActive = filter.trim().length > 0;
  const typeKey = (type: string) => `${group.key}::${type}`;
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
      className="dataset-group"
      data-testid={`dataset-group-${group.key}`}
      data-phantom={group.phantom ? "true" : undefined}
      data-unattributed={group.unattributed ? "true" : undefined}
    >
      <div className="dataset-group-header">
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
      {groupTypes(group).map((type) => {
        const rows = group.rows.filter((r) => r.resourceType === type);
        const matching = rows.filter(matches);
        if (filterActive && matching.length === 0) return null;
        // OQ-1 RESOLVED: type groups default OPEN when ≤ 3 resources,
        // COLLAPSED with count otherwise. Filter active → auto-expand
        // + bypass the row cap (gemini C: matches never hide).
        const userCollapsed = collapsedTypes.has(typeKey(type));
        const userExpanded = expandedTypes.has(typeKey(type));
        const uncapped = uncappedTypes.has(typeKey(type));
        // OQ-1: small groups (≤3) default open; big groups default
        // collapsed until opened (userCollapsed wins over everything
        // except an active filter). capBypassed = show-more lifted the
        // 25-row cap for THIS group (opening alone stays capped).
        const isOpen = filterActive
          ? true
          : userCollapsed
            ? false
            : userExpanded || rows.length <= 3;
        const capBypassed = filterActive || uncapped;
        const candidates = filterActive ? matching : rows;
        const visible = isOpen
          ? capBypassed
            ? candidates
            : candidates.slice(0, typeRowCap)
          : [];
        const hidden = candidates.length - visible.length;
        return (
          <div
            key={type}
            className="dataset-type-group"
            data-testid={`dataset-type-${group.key}-${type}`}
          >
            <button
              type="button"
              className="dataset-type-toggle"
              data-testid={`dataset-type-toggle-${group.key}-${type}`}
              onClick={() => {
                if (!isOpen) {
                  // Opening a big (default-collapsed) group: explicit
                  // expand flag — renders the capped list + show-more.
                  const ex = new Set(expandedTypes);
                  ex.add(typeKey(type));
                  setExpandedTypes(ex);
                } else {
                  // Collapse any open group (explicitly expanded or
                  // small-default); expanding again reopens it.
                  const next = new Set(collapsedTypes);
                  next.add(typeKey(type));
                  setCollapsedTypes(next);
                }
              }}
            >
              {isOpen ? "▾" : "▸"} {type} ({rows.length})
            </button>
            {isOpen &&
              visible.map((r) => (
                <div
                  key={r.index}
                  className="dataset-row"
                  data-testid={`dataset-row-${r.index}`}
                >
                  <span className="dataset-row-id">
                    {r.resourceType}/{r.id}
                    {group.unattributed && (
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
                      onClick={() => onEditResource?.(r.index)}
                      title="Edit in Resource Builder"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      data-testid={`dataset-delete-${r.index}`}
                      onClick={() => onDelete(r.index)}
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
                data-testid={`dataset-more-${group.key}-${type}`}
                onClick={() => {
                  const ex = new Set(uncappedTypes);
                  ex.add(typeKey(type));
                  setUncappedTypes(ex);
                }}
              >
                + show {hidden} more
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

function patientHint(resource: Record<string, unknown>): string | null {
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

const DEFAULT_NDJSON = [
  JSON.stringify({ resourceType: "Patient", id: "p1", gender: "female", name: [{ given: ["Ann"] }] }),
  JSON.stringify({ resourceType: "Patient", id: "p2", gender: "male", name: [{ given: ["Bob"] }] }),
  JSON.stringify({ resourceType: "Patient", id: "p3", gender: "female" }),
].join("\n");

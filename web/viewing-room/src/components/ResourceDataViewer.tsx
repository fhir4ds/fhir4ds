/**
 * ResourceDataViewer: Browse-tab tree over the in-memory parsed resources.
 *
 * VENDORED GENERALIZED EXTRACTION of cql-clinic's PatientDataViewer.tsx
 * (attribution: web/cql-clinic/src/components/PatientDataViewer.tsx).
 * Divergences per design §4.5:
 *   - No patient pivot / no DuckDB round-trip: renders the parsed
 *     in-memory resources array directly (the editor text is the source
 *     of truth; staging happens at Run).
 *   - Resource-type groups at the TOP level (datasets may contain no
 *     Patient at all, e.g. Observation-only samples).
 *   - highlightTypes is wired to the ViewDefinition's target resource —
 *     the type the current view selects is visually distinguished.
 *   - dataVersion bumps re-parse from editor content (caller passes the
 *     newly parsed array).
 * Kept as-is: filter box, expand/collapse-all, JsonTree rendering,
 * resource labels/meta (coding display, effective dates), selection hooks.
 */

import { useMemo, useRef, useState } from "react";

export interface ResourceDataViewerProps {
  resources: Array<Record<string, unknown>>;
  /** Resource types to visually highlight (VD target resource). */
  highlightTypes?: string[] | null;
}

/**
 * Per-group initial render cap. Large datasets (e.g. the OMOP medication
 * bundle: 4,356 resources including 2,843 ConceptMap chunks) must not
 * eagerly build the whole list; the rest renders on demand.
 */
const INITIAL_RENDER_CAP = 200;

export function ResourceDataViewer({ resources, highlightTypes = null }: ResourceDataViewerProps) {
  const [filterText, setFilterText] = useState("");
  // Groups start collapsed; "Expand all" / "Collapse all" forces every group
  // open/closed via a generation bump (groups remain user-toggleable).
  const [expandTarget, setExpandTarget] = useState(false);
  const [expandGen, setExpandGen] = useState(0);
  const toggleAll = () => {
    setExpandTarget((v) => !v);
    setExpandGen((g) => g + 1);
  };

  const filteredResources = useMemo(() => {
    const query = filterText.trim().toLowerCase();
    if (!query) return resources;
    return resources.filter((r) => JSON.stringify(r).toLowerCase().includes(query));
  }, [filterText, resources]);

  const resourceGroups = useMemo(() => {
    const groups = new Map<string, Array<Record<string, unknown>>>();
    for (const resource of filteredResources) {
      const type = String(resource.resourceType ?? "Unknown");
      const existing = groups.get(type) ?? [];
      existing.push(resource);
      groups.set(type, existing);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [filteredResources]);

  return (
    <div className="resource-viewer" data-testid="resource-viewer">
      <div className="resource-viewer-tools">
        <input
          className="resource-viewer-filter"
          type="search"
          placeholder="Filter resources"
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          aria-label="Filter resources"
        />
        <button className="resource-viewer-tree-toggle" onClick={toggleAll}>
          {expandTarget ? "Collapse all" : "Expand all"}
        </button>
      </div>

      <div className="resource-viewer-body">
        {resources.length === 0 && (
          <div className="resource-viewer-empty">No resources parsed — check the editor.</div>
        )}
        {resources.length > 0 && (
          <>
            <div className="resource-viewer-summary">
              {filteredResources.length} of {resources.length} resource{resources.length !== 1 ? "s" : ""}
              {" · "}
              {resourceGroups.map(([type, items]) => `${type} (${items.length})`).join(", ")}
            </div>
            <div className="resource-viewer-tree">
              {resourceGroups.map(([type, items]) => (
                <ResourceGroup
                  key={type}
                  type={type}
                  items={items}
                  expandTarget={expandTarget}
                  expandGen={expandGen}
                  highlighted={Boolean(highlightTypes?.includes(type))}
                />
              ))}
              {resourceGroups.length === 0 && (
                <div className="resource-viewer-empty">No resources match "{filterText}".</div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ResourceGroup({
  type,
  items,
  expandTarget,
  expandGen,
  highlighted,
}: {
  type: string;
  items: Array<Record<string, unknown>>;
  expandTarget: boolean;
  expandGen: number;
  highlighted: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  // Uncontrolled open state kept in sync with the DOM `toggle` event so
  // manual clicks and the global Expand/Collapse-all button coexist.
  const [open, setOpen] = useState(expandTarget);
  const lastGen = useRef(expandGen);
  if (lastGen.current !== expandGen) {
    lastGen.current = expandGen;
    if (open !== expandTarget) setOpen(expandTarget);
  }
  const visible = showAll ? items : items.slice(0, INITIAL_RENDER_CAP);
  return (
    <details
      className={`resource-viewer-group${highlighted ? " resource-highlight" : ""}`}
      open={open}
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
      data-testid={`resource-group-${type}`}
    >
      <summary>
        <span className="tree-caret" />
        <span className="resource-viewer-type">{type}</span>
        <span className="resource-viewer-count">{items.length}</span>
      </summary>
      <div className="resource-viewer-list">
        {visible.map((resource, index) => {
          const key = `${resource.resourceType ?? "Unknown"}-${resource.id ?? index}`;
          return <ResourceItem key={key} resource={resource} />;
        })}
        {!showAll && items.length > INITIAL_RENDER_CAP && (
          <button
            type="button"
            className="resource-viewer-show-more"
            onClick={() => setShowAll(true)}
          >
            Show all {items.length} {type} resources
          </button>
        )}
      </div>
    </details>
  );
}

/**
 * One resource row. The JSON tree mounts ONLY when the row is opened —
 * a collapsed <details> still mounts its children, so rendering every
 * resource's tree eagerly built ~1.9M DOM nodes for the 4,356-resource
 * medication bundle and blocked the main thread for tens of seconds.
 */
function ResourceItem({ resource }: { resource: Record<string, unknown> }) {
  // Uncontrolled: the browser owns the open attribute; state only gates
  // mounting the (potentially large) JSON tree.
  const [mounted, setMounted] = useState(false);
  return (
    <details
      className="resource-viewer-item"
      onToggle={(e) => setMounted((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary>
        <span className="tree-caret" />
        <span className="resource-viewer-title">{resourceLabel(resource)}</span>
        <span className="resource-viewer-meta">{resourceMeta(resource)}</span>
      </summary>
      {mounted ? <JsonTree value={resource} expanded /> : null}
    </details>
  );
}

function resourceLabel(resource: Record<string, unknown>): string {
  const type = resource.resourceType ?? "Resource";
  const id = resource.id ? `/${resource.id}` : "";
  const code = codingDisplay(resource);
  return code ? `${type}${id} · ${code}` : `${type}${id}`;
}

function resourceMeta(resource: Record<string, unknown>): string {
  const r = resource as Record<string, any>;
  const candidates = [
    r.effectiveDateTime,
    r.authoredOn,
    r.recordedDate,
    r.onsetDateTime,
    r.performedDateTime,
    r.period?.start,
    r.effectivePeriod?.start,
  ].filter(Boolean);
  return candidates.length > 0 ? String(candidates[0]) : "";
}

function codingDisplay(resource: Record<string, any>): string {
  const coding =
    resource.code?.coding?.[0] ??
    resource.type?.[0]?.coding?.[0] ??
    resource.category?.[0]?.coding?.[0];
  return coding?.display ?? coding?.code ?? resource.code?.text ?? "";
}

/**
 * Children rendered per JSON node before the "show more" control appears.
 * A ConceptMap can carry 100k+ elements; rendering them in one commit
 * builds ~1M DOM nodes and freezes the tab. Paging every node keeps any
 * expansion to ~CHILD_PAGE * nodes-per-entry.
 */
const CHILD_PAGE = 100;
/** Offer a one-click "show all" only when the remainder is small enough. */
const SHOW_ALL_MAX = 1000;

function JsonTree({
  value,
  name,
  expanded,
}: {
  value: unknown;
  name?: string;
  expanded: boolean;
}) {
  const isObject = value !== null && typeof value === "object";
  const entries: Array<readonly [string, unknown]> = isObject
    ? Array.isArray(value)
      ? value.map((item, index) => [String(index), item] as const)
      : Object.entries(value as Record<string, unknown>)
    : [];
  // Hook must run unconditionally (scalar rows early-return below).
  const [visibleCount, setVisibleCount] = useState(() =>
    Math.min(entries.length, CHILD_PAGE),
  );

  if (!isObject) {
    return (
      <div className="json-tree-row">
        {name && <span className="json-tree-key">{name}: </span>}
        <span className={`json-tree-value json-tree-${typeof value}`}>{formatScalar(value)}</span>
      </div>
    );
  }

  const label = Array.isArray(value)
    ? `Array(${entries.length})`
    : `Object(${entries.length})`;
  const shown = entries.slice(0, visibleCount);
  const remaining = entries.length - shown.length;

  return (
    <details className="json-tree-node" open={expanded}>
      <summary>
        <span className="tree-caret" />
        {name && <span className="json-tree-key">{name}: </span>}
        <span className="json-tree-kind">{label}</span>
      </summary>
      <div className="json-tree-children">
        {shown.map(([key, child]) => (
          <JsonTree key={key} name={key} value={child} expanded={expanded} />
        ))}
        {remaining > 0 && (
          <div className="json-tree-more">
            <button
              type="button"
              onClick={() =>
                setVisibleCount((n) => Math.min(entries.length, n + CHILD_PAGE))
              }
            >
              Show next {Math.min(CHILD_PAGE, remaining)} ({remaining} more)
            </button>
            {remaining <= SHOW_ALL_MAX && (
              <button type="button" onClick={() => setVisibleCount(entries.length)}>
                Show all {entries.length}
              </button>
            )}
          </div>
        )}
      </div>
    </details>
  );
}

function formatScalar(value: unknown): string {
  if (typeof value === "string") return `"${value}"`;
  if (value === null) return "null";
  return String(value);
}

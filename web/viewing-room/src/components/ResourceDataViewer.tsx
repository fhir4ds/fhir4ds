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

import { useMemo, useState } from "react";

export interface ResourceDataViewerProps {
  resources: Array<Record<string, unknown>>;
  /** Resource types to visually highlight (VD target resource). */
  highlightTypes?: string[] | null;
}

export function ResourceDataViewer({ resources, highlightTypes = null }: ResourceDataViewerProps) {
  const [filterText, setFilterText] = useState("");
  const [expanded, setExpanded] = useState(true);

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
        <button className="resource-viewer-tree-toggle" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Collapse all" : "Expand all"}
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
                <details
                  className={`resource-viewer-group${highlightTypes?.includes(type) ? " resource-highlight" : ""}`}
                  key={type}
                  open={expanded}
                  data-testid={`resource-group-${type}`}
                >
                  <summary>
                    <span className="tree-caret" />
                    <span className="resource-viewer-type">{type}</span>
                    <span className="resource-viewer-count">{items.length}</span>
                  </summary>
                  <div className="resource-viewer-list">
                    {items.map((resource, index) => {
                      const key = `${resource.resourceType ?? "Unknown"}-${resource.id ?? index}`;
                      return (
                        <details
                          className="resource-viewer-item"
                          key={key}
                          open={expanded}
                        >
                          <summary>
                            <span className="tree-caret" />
                            <span className="resource-viewer-title">{resourceLabel(resource)}</span>
                            <span className="resource-viewer-meta">{resourceMeta(resource)}</span>
                          </summary>
                          <JsonTree value={resource} expanded={expanded} />
                        </details>
                      );
                    })}
                  </div>
                </details>
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

function JsonTree({
  value,
  name,
  expanded,
}: {
  value: unknown;
  name?: string;
  expanded: boolean;
}) {
  if (value === null || typeof value !== "object") {
    return (
      <div className="json-tree-row">
        {name && <span className="json-tree-key">{name}: </span>}
        <span className={`json-tree-value json-tree-${typeof value}`}>{formatScalar(value)}</span>
      </div>
    );
  }

  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item] as const)
    : Object.entries(value as Record<string, unknown>);
  const label = Array.isArray(value)
    ? `Array(${entries.length})`
    : `Object(${entries.length})`;

  return (
    <details className="json-tree-node" open={expanded}>
      <summary>
        <span className="tree-caret" />
        {name && <span className="json-tree-key">{name}: </span>}
        <span className="json-tree-kind">{label}</span>
      </summary>
      <div className="json-tree-children">
        {entries.map(([key, child]) => (
          <JsonTree key={key} name={key} value={child} expanded={expanded} />
        ))}
      </div>
    </details>
  );
}

function formatScalar(value: unknown): string {
  if (typeof value === "string") return `"${value}"`;
  if (value === null) return "null";
  return String(value);
}

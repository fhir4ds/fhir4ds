import { useEffect, useState } from "react";
import type { QueryResult } from "../../hooks/useDuckDB";
import { RESOURCE_TYPES } from "../../lib/search-presets";
import { JsonViewer } from "../JsonViewer";

interface RawDataSectionProps {
  /** Whether the data is ingested and ready to browse. */
  ready: boolean;
  /** Function that executes a SQL query against the in-browser DuckDB. */
  executeQuery: (sql: string) => Promise<QueryResult>;
}

/**
 * §2: Browse the raw published FHIR resources one at a time. Pick a resource
 * type and provider, page through the resources, see the actual JSON shape
 * that publishers ship in their NDJSON.
 *
 * The data comes from the `resources` table populated during ingest. Each row
 * is one FHIR resource; the `resource` column holds the raw JSON.
 */
export function RawDataSection({ ready, executeQuery }: RawDataSectionProps) {
  const [resourceType, setResourceType] = useState("Slot");
  const [provider, setProvider] = useState("");
  const [index, setIndex] = useState(0);
  const [count, setCount] = useState(0);
  const [resource, setResource] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset to first resource whenever the type or provider filter changes
  useEffect(() => {
    setIndex(0);
  }, [resourceType, provider]);

  // Load count + current resource whenever filters or index change
  useEffect(() => {
    if (!ready) return;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const providerFilter = provider
          ? `AND id LIKE '${provider}-%'`
          : "";
        const countResult = await executeQuery(
          `SELECT COUNT(*) AS n FROM resources WHERE resourceType = '${resourceType}' ${providerFilter};`,
        );
        const newCount = Number(countResult.rows[0]?.[0] ?? 0);
        setCount(newCount);
        const safeIndex = Math.min(index, Math.max(0, newCount - 1));
        if (newCount === 0) {
          setResource(null);
          return;
        }
        const result = await executeQuery(
          `SELECT resource FROM resources WHERE resourceType = '${resourceType}' ${providerFilter} LIMIT 1 OFFSET ${safeIndex};`,
        );
        const raw = result.rows[0]?.[0];
        setResource(raw ? JSON.parse(typeof raw === "string" ? raw : JSON.stringify(raw)) : null);
      } catch (e: any) {
        setError(e?.message ?? String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [ready, resourceType, provider, index, executeQuery]);

  if (!ready) {
    return (
      <div className="widget widget--pending">
        Connect to a publisher above to browse raw resources.
      </div>
    );
  }

  const providers = ["allina", "childrens", "mayo", "hennepin", "fairview"];

  return (
    <div className="widget">
      <div className="raw-controls">
        <label className="raw-control">
          <span>Resource type</span>
          <select value={resourceType} onChange={(e) => setResourceType(e.target.value)}>
            {RESOURCE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="raw-control">
          <span>Publisher</span>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="">(any)</option>
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <div className="raw-pager">
          <button onClick={() => setIndex((i) => Math.max(0, i - 1))} disabled={index === 0}>
            ‹ prev
          </button>
          <span className="raw-pager__count">
            {count === 0 ? "0 of 0" : `${index + 1} of ${count.toLocaleString()}`}
          </span>
          <button
            onClick={() => setIndex((i) => Math.min(count - 1, i + 1))}
            disabled={index >= count - 1}
          >
            next ›
          </button>
        </div>
      </div>

      {error && <div className="widget__error">{error}</div>}

      <div className="raw-viewer">
        {loading && <div className="widget__pending">Loading…</div>}
        {!loading && !resource && (
          <div className="widget__pending">No resources match this filter.</div>
        )}
        {!loading && resource && <JsonViewer value={resource} maxHeight="480px" />}
      </div>
    </div>
  );
}

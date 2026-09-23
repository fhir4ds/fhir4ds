import { useMemo, useState } from "react";
import type { DatasetSpec } from "../lib/protocol";

export function DatasetPane({
  dataset,
  onDatasetChange,
  onEditResource,
}: {
  dataset: DatasetSpec | null;
  onDatasetChange: (ds: DatasetSpec | null) => void;
  /** C3-U3: asks the builder to prefill from row i. */
  onEditResource?: (index: number) => void;
}) {
  const [text, setText] = useState(DEFAULT_NDJSON);

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

  const stats = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of parsed.resources) {
      const rt = r.resourceType ?? "Unknown";
      counts[rt] = (counts[rt] ?? 0) + 1;
    }
    return counts;
  }, [parsed]);

  return (
    <section className="pane" data-testid="dataset-pane">
      <header className="pane-header">
        <h2>Dataset</h2>
        <button
          data-testid="load-dataset"
          disabled={!!parsed.error || !parsed.resources.length}
          onClick={() =>
            onDatasetChange({ resources: parsed.resources })
          }
        >
          Use dataset ({parsed.resources.length})
        </button>
      </header>
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
      {Object.keys(stats).length > 0 && (
        <div className="dataset-stats" data-testid="dataset-stats">
          {Object.entries(stats).map(([rt, n]) => (
            <span key={rt} className="stat-chip">
              {rt}: {n}
            </span>
          ))}
        </div>
      )}
      {dataset && (
        <div className="dataset-loaded" data-testid="dataset-loaded">
          Active: {dataset.resources?.length ?? 0} resources
        </div>
      )}
      {dataset && (dataset.resources?.length ?? 0) > 0 && (
        <div className="dataset-rows" data-testid="dataset-rows">
          {(dataset.resources ?? []).map((r, i) => {
            const rec = r as Record<string, unknown>;
            const rt = typeof rec.resourceType === "string" ? rec.resourceType : "?";
            const id = typeof rec.id === "string" ? rec.id : "";
            return (
              <div key={i} className="dataset-row" data-testid={`dataset-row-${i}`}>
                <span className="dataset-row-id">{rt}/{id}</span>
                <span className="dataset-row-actions">
                  <button
                    type="button"
                    data-testid={`dataset-edit-${i}`}
                    onClick={() => onEditResource?.(i)}
                    title="Edit in Resource Builder"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    data-testid={`dataset-delete-${i}`}
                    onClick={() => {
                      // Immutable replace (INV-C3-3): never mutate in place.
                      const resources = (dataset.resources ?? []).filter(
                        (_, j) => j !== i,
                      );
                      onDatasetChange({ ...dataset, resources });
                    }}
                    title="Remove from dataset"
                  >
                    ×
                  </button>
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

const DEFAULT_NDJSON = [
  JSON.stringify({ resourceType: "Patient", id: "p1", gender: "female", name: [{ given: ["Ann"] }] }),
  JSON.stringify({ resourceType: "Patient", id: "p2", gender: "male", name: [{ given: ["Bob"] }] }),
  JSON.stringify({ resourceType: "Patient", id: "p3", gender: "female" }),
].join("\n");

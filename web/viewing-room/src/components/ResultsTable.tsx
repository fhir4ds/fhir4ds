/**
 * Results table: NULL chips, JSON-array rendering for collection columns,
 * 0-row hint naming ViewDefinition.resource filtering (design §4).
 */

interface Props {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  ranAt: number | null;
  vdResource: string | null;
  loadedTypes: string;
}

function Cell({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="null-chip">null</span>;
  }
  if (typeof value === "object") {
    return <span className="json-cell">{JSON.stringify(value)}</span>;
  }
  if (typeof value === "boolean") {
    return <span>{String(value)}</span>;
  }
  return <span>{String(value)}</span>;
}

export function ResultsTable({ columns, rows, ranAt, vdResource, loadedTypes }: Props) {
  if (!ranAt) {
    return <div className="empty-hint">Run the view to see results.</div>;
  }
  const rowTypes = [...new Set(rows.map((r) => (typeof r.resourceType === "string" ? r.resourceType : null)).filter(Boolean))] as string[];
  const shownTypes = rows.length ? rowTypes.join(", ") : loadedTypes;
  return (
    <div className="table-wrap" data-testid="output-table">
      <div className="row-count">
        {rows.length} row{rows.length === 1 ? "" : "s"}
        {shownTypes ? ` · types: ${shownTypes}` : ""}
      </div>
      {rows.length === 0 ? (
        <div className="empty-hint" data-testid="empty-hint">
          0 rows — resources filtered by ViewDefinition.resource
          {vdResource ? `="${vdResource}"` : ""}
          {shownTypes ? ` (loaded: ${shownTypes})` : " or empty collections"}.
        </div>
      ) : (
        <table className="results">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {columns.map((c) => (
                  <td key={c}>
                    <Cell value={row[c]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

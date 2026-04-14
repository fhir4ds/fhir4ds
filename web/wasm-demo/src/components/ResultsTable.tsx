import type React from "react";
import { useState } from "react";
import { isAuditCell, generateNarrative, type AuditCell } from "../lib/narrative";
import { EvidenceModal } from "./EvidenceModal";

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  rowCount: number;
  executionTimeMs: number;
}

interface ResultsTableProps {
  result: QueryResult | null;
  error: string | null;
  isLoading: boolean;
  /** Optional callback when a row is clicked (e.g. to select a patient) */
  onRowClick?: (row: unknown[]) => void;
  /** Current selected row identifier (usually first column) */
  selectedRowId?: string | null;
}

export function ResultsTable({ result, error, isLoading, onRowClick, selectedRowId }: ResultsTableProps) {
  const [modalCell, setModalCell] = useState<{ cell: AuditCell; columnName: string } | null>(null);

  return (
    <div className="results-pane">
      <div className="pane-header">
        <span className="pane-title">Results</span>
        {result && (
          <span className="pane-meta">
            {result.rowCount} row{result.rowCount !== 1 ? "s" : ""} in{" "}
            {result.executionTimeMs.toFixed(1)}ms
          </span>
        )}
      </div>
      <div className="pane-body results-body">
        {isLoading && <div className="results-message">Executing query…</div>}
        {error && <div className="results-error">{error}</div>}
        {!isLoading && !error && !result && (
          <div className="results-message">
            Run a query to see results here.
          </div>
        )}
        {result && !error && (
          <div className="table-wrapper">
            <table className="results-table">
              <thead>
                <tr>
                  {result.columns.map((col, i) => (
                    <th key={i}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, ri) => {
                  const isSelected = selectedRowId && String(row[0]) === selectedRowId;
                  return (
                    <tr 
                      key={ri} 
                      onClick={() => onRowClick?.(row)}
                      className={onRowClick ? "clickable-row" : ""}
                      style={{ 
                        cursor: onRowClick ? "pointer" : "default",
                        background: isSelected ? "rgba(56, 189, 248, 0.1)" : undefined
                      }}
                    >
                      {row.map((cell, ci) => (
                        <td key={ci}>
                          {renderCell(cell, result.columns[ci], setModalCell)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {modalCell && (
        <EvidenceModal
          cell={modalCell.cell}
          columnName={modalCell.columnName}
          onClose={() => setModalCell(null)}
        />
      )}
    </div>
  );
}

function renderCell(
  value: unknown,
  columnName: string,
  onAuditClick: (info: { cell: AuditCell; columnName: string }) => void,
): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="cell-null">[]</span>;
  }
  if (isAuditCell(value)) {
    return (
      <AuditBadge
        cell={value}
        columnName={columnName}
        onClick={() => onAuditClick({ cell: value, columnName })}
      />
    );
  }
  if (typeof value === "boolean") {
    return <BoolBadge value={value} />;
  }
  if (typeof value === "number") {
    return <span className="cell-number">{formatNumber(value)}</span>;
  }
  
  // Refined array/object summarization for clinical data
  const summary = summarizeValue(value);
  const tooltip = typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
  
  if (typeof value === 'object') {
    return <span className="cell-object" title={tooltip}>{summary}</span>;
  }
  
  return summary;
}

/** 
 * Summarizes clinical FHIR data for the results grid.
 * Returns [] for empty lists and [Type/ID, ...] for populated lists.
 */
function summarizeValue(val: unknown): string {
  if (val === null || val === undefined) return "[]";

  let data = val;
  
  // 1. Force convert DuckDB/Arrow proxies to plain JSON if possible
  if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
    try {
      if (typeof (val as any).toJSON === 'function') {
        data = (val as any).toJSON();
      }
    } catch { /* ignore */ }
  }

  // 2. Detect "List-like" objects (numeric keys)
  if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
    const keys = Object.keys(data);
    const numericKeys = keys.filter(k => !isNaN(Number(k)));
    // If it has numeric keys, treat it as an array
    if (numericKeys.length > 0) {
      data = numericKeys.sort((a, b) => Number(a) - Number(b)).map(k => (data as any)[k]);
    } else if (keys.length === 0 || (keys.length === 1 && keys[0] === 'isValid')) {
      // It's an empty proxy object
      return "[]";
    }
  }

  // 3. Process as Array
  if (Array.isArray(data)) {
    if (data.length === 0) return "[]";
    const items = data.map(item => summarizeLeaf(item));
    return `[${items.join(", ")}]`;
  }

  // 4. Process as single Object
  if (typeof data === 'object' && data !== null) {
    return summarizeLeaf(data);
  }

  return String(data);
}

/** Summarize a single item/object into a short string reference or label */
function summarizeLeaf(item: any): string {
  if (item === null || item === undefined) return "null";
  if (typeof item !== 'object') return String(item);

  // Deep convert to plain object
  let obj = item;
  try {
    if (typeof item.toJSON === 'function') obj = item.toJSON();
  } catch { /* ignore */ }

  // 1. FHIR Resource / Reference
  if (obj.resourceType && obj.id) return `${obj.resourceType}/${obj.id}`;
  if (obj.reference && typeof obj.reference === 'string') return obj.reference;
  
  // 2. Common clinical labels
  if (obj.Display && typeof obj.Display === 'string') return obj.Display;
  if (obj.display && typeof obj.display === 'string') return obj.display;
  if (obj.text && typeof obj.text === 'string') return obj.text;
  if (obj.code && typeof obj.code === 'string') return obj.code;

  // 3. Fallback: filter internal metadata and show first key
  const keys = Object.keys(obj).filter(k => 
    typeof obj[k] !== 'function' && !k.startsWith('_') && k !== 'isValid'
  );
  if (keys.length > 0) {
    const firstVal = String(obj[keys[0]]);
    return `${keys[0]}: ${firstVal.length > 15 ? firstVal.substring(0, 15) + "…" : firstVal}`;
  }

  return "{…}";
}

function AuditBadge({
  cell,
  columnName,
  onClick,
}: {
  cell: AuditCell;
  columnName: string;
  onClick: () => void;
}) {
  const narrative = generateNarrative(columnName, cell.evidence ?? [], cell.result);
  const tooltipText = narrative.join("\n");

  return (
    <span className="audit-cell" title={tooltipText} onClick={(e) => { e.stopPropagation(); onClick(); }}>
      <span className={`cell-bool ${cell.result ? "cell-bool--true" : "cell-bool--false"}`}>
        {cell.result ? "✓ true" : "✗ false"}
      </span>
      <span className="audit-icon">🔍</span>
    </span>
  );
}

function BoolBadge({ value }: { value: boolean }) {
  return (
    <span
      className={`cell-bool ${value ? "cell-bool--true" : "cell-bool--false"}`}
    >
      {value ? "✓ true" : "✗ false"}
    </span>
  );
}

function formatNumber(val: number): string {
  if (Number.isInteger(val)) return val.toString();
  return val.toFixed(2);
}

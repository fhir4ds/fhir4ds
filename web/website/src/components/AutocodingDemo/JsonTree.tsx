/**
 * Collapsible JSON resource tree — extracted from the SDC demo's
 * PatientDataViewer (web/wasm-demo) so the docs examples share the same
 * resource-view experience. Pure React <details>-based recursion; styling
 * lives in styles.css (adapted to Docusaurus CSS variables).
 */
import React from 'react';

function formatScalar(value: unknown): string {
  if (typeof value === 'string') return `"${value}"`;
  if (value === null) return 'null';
  return String(value);
}

export function JsonTree({
  value,
  name,
  expanded = false,
  depth = 0,
  collapseKey,
}: {
  value: unknown;
  name?: string;
  expanded?: boolean;
  depth?: number;
  /** Node names that render collapsed by default (e.g. audit "extension"). */
  collapseKey?: string;
}) {
  if (value === null || typeof value !== 'object') {
    return (
      <div className="json-tree-row">
        {name && <span className="json-tree-key">{name}: </span>}
        <span className={`json-tree-value json-tree-${typeof value}`}>
          {formatScalar(value)}
        </span>
      </div>
    );
  }

  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item] as const)
    : Object.entries(value as Record<string, unknown>);
  const label = Array.isArray(value)
    ? `Array(${entries.length})`
    : `Object(${entries.length})`;
  // Top level (and shallow nests) start expanded; deep nodes collapsed.
  const open = name === collapseKey ? false : expanded || depth < 2;

  return (
    <details className="json-tree-node" open={open}>
      <summary>
        <span className="json-tree-caret" />
        {name && <span className="json-tree-key">{name}: </span>}
        <span className="json-tree-kind">{label}</span>
      </summary>
      <div className="json-tree-children">
        {entries.map(([key, child]) => (
          <JsonTree
            key={key}
            name={key}
            value={child}
            depth={depth + 1}
            expanded={expanded}
            collapseKey={collapseKey}
          />
        ))}
      </div>
    </details>
  );
}

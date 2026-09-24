import { useMemo, useState } from "react";
import { workerRequest } from "./BootOverlay";
import type { AstNode, ParseResult } from "../lib/protocol";

/**
 * C2-U2: AstPane — statement-level AST tree for the active library.
 *
 * parse_cql(include_ast=true) → one serialized tree per define
 * ({"kind", "children"} nodes). The pane renders a collapsible tree;
 * the SQL↔CTE map (AstPane bottom section) lists the population SQL
 * CTE names so users can correlate defines to CTEs. Lineage shown here
 * is client-derived (non-authoritative) — no 'derived' badge needed at
 * this granularity since the whole pane IS derived.
 */

interface Props {
  cqlText: string;
}

function AstTreeNode({
  label,
  node,
  depth,
}: {
  label: string;
  node: unknown;
  depth: number;
}) {
  const [open, setOpen] = useState(depth < 2);
  if (node === null || typeof node !== "object") {
    const text =
      node === null
        ? "null"
        : typeof node === "string"
          ? `"${node}"`
          : String(node);
    return (
      <div className="ast-leaf" style={{ marginLeft: depth * 12 }}>
        <span className="ast-key">{label}</span>
        <span className="ast-value">{text}</span>
      </div>
    );
  }
  const isNode = "kind" in (node as Record<string, unknown>);
  const title = isNode
    ? (node as AstNode).kind
    : label;
  const children = isNode
    ? Object.entries((node as AstNode).children ?? {})
    : Object.entries(node as Record<string, unknown>);
  if (children.length === 0) {
    return (
      <div className="ast-leaf" style={{ marginLeft: depth * 12 }}>
        <span className="ast-kind">{title}</span>
      </div>
    );
  }
  return (
    <div className="ast-branch" style={{ marginLeft: depth * 12 }}>
      <button
        type="button"
        className="ast-toggle"
        data-testid="ast-toggle"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "▾" : "▸"} {title}
        {isNode && (
          <span className="ast-kind-badge" data-testid={`ast-kind-${(node as AstNode).kind}`}>
            {(node as AstNode).kind}
          </span>
        )}
      </button>
      {open &&
        children.map(([k, v]) => (
          <AstTreeNode key={k} label={k} node={v} depth={depth + 1} />
        ))}
    </div>
  );
}

export function AstTree({ cqlText }: Props) {
  const [parse, setParse] = useState<ParseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [filterText, setFilterText] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const resp = await workerRequest({
        type: "parse_cql",
        text: cqlText,
        include_ast: true,
      });
      if (resp?.ok && resp.envelope) {
        setParse(JSON.parse(resp.envelope));
      }
    } finally {
      setLoading(false);
    }
  };

  const statements = useMemo(() => {
    const all = Object.entries(parse?.ast?.statements ?? {});
    const q = filterText.trim().toLowerCase();
    return q ? all.filter(([name]) => name.toLowerCase().includes(q)) : all;
  }, [parse, filterText]);

  return (
    <div className="ast-inline" data-testid="ast-inline">
      <div className="inspection-row ast-filter-row">
        <button
          type="button"
          data-testid="ast-load"
          onClick={load}
          disabled={loading}
        >
          {loading ? "…" : "Parse AST"}
        </button>
        <input
          data-testid="ast-filter"
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          placeholder="filter defines"
          aria-label="filter defines"
        />
      </div>
      {parse && !parse.ok && (
        <div className="diag-list" data-testid="ast-error">
          {(parse.diagnostics ?? []).map((d, i) => (
            <div key={i} className="diag-row diag-error">
              {d.message}
            </div>
          ))}
        </div>
      )}
      {statements.length > 0 && (
        <div className="ast-trees" data-testid="ast-trees">
          {statements.map(([name, tree]) => (
            <div key={name} className="ast-tree">
              <div className="ast-def-name" data-testid={`ast-def-${name}`}>
                define {name}
              </div>
              <AstTreeNode label={name} node={tree} depth={0} />
            </div>
          ))}
        </div>
      )}
      {parse?.ok && statements.length === 0 && (
        <p className="ast-empty">No defines in library.</p>
      )}
    </div>
  );
}

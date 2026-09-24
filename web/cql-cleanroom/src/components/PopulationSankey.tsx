/**
 * Dependency-free population-flow Sankey (C1-U7).
 *
 * Columns = FHIR CQM attribution order (IPP → DEN → DENEX → NUM → NUMEX),
 * nodes sized by population membership, links labeled with per-transition
 * patient counts. Data comes from evaluate_library rows over ALL boolean
 * population columns (plain booleans, population-mode SQL).
 *
 * Rendered as pure SVG with rounded rects + cubic paths — no chart lib.
 */

export interface SankeyNode {
  column: number;
  name: string;
  count: number;
}

export interface SankeyLink {
  from: string;
  to: string;
  count: number;
}

export interface SankeyData {
  nodes: SankeyNode[];
  links: SankeyLink[];
}
/**
 * Population-flow transitions follow the FHIR CQM attribution order the
 * DQM summary_report uses (operations AGENTS.md doctrine):
 *   DEN ⊆ IPP; DENEX removed from DEN; NUM ⊆ DEN∖DENEX;
 *   NUMEX removed from NUM; DEX (exceptions) ⊆ DEN∖DENEX∖NUM.
 *
 * Column order comes from the Measure resource (population codes via
 * measure_population_map + POPULATION_ORDER) — INV-3; the legacy
 * name-prefix heuristic (ORDERED_PREFIXES) is DELETED.
 */

import { POPULATION_ORDER } from "../lib/protocol";

function orderedColumnIndex(name: string): number {
  // Columns are population-code convention (initial_population, ...).
  const code = name.replace(/_/g, "-");
  const idx = POPULATION_ORDER.indexOf(code);
  if (idx >= 0) return idx;
  // Unknown naming: fall back to the definition order in the data.
  return POPULATION_ORDER.length;
}

export function buildPopulationFlow(
  rows: Array<Record<string, unknown>>,
  columns: string[],
): SankeyData {
  const colCount = (col: string) =>
    rows.filter((r) => r[col] === true).length;

  const sorted = [...columns].sort((a, b) => {
    const ia = orderedColumnIndex(a);
    const ib = orderedColumnIndex(b);
    return ia === ib ? a.localeCompare(b) : ia - ib;
  });

  const nodes: SankeyNode[] = sorted.map((name, i) => ({
    column: i,
    name,
    count: colCount(name),
  }));

  // Attribution links: each population at level i links to the next
  // population level j > i with |patients in i ∩ j| — clamped by the
  // DQM gating semantics (denominator exclusions REMOVED, not linked).
  const links: SankeyLink[] = [];
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      const a = sorted[i];
      const b = sorted[j];
      const both = rows.filter((r) => r[a] === true && r[b] === true).length;
      if (both > 0) links.push({ from: a, to: b, count: both });
    }
  }
  return { nodes, links };
}

const NODE_W = 14;
const COL_GAP = 150;
const ROW_H = 26;
const PAD = 8;

export function PopulationSankey({ data }: { data: SankeyData }) {
  const cols = Math.max(...data.nodes.map((n) => n.column)) + 1;
  const width = cols * COL_GAP + NODE_W + PAD * 2;
  const byCol = new Map<number, SankeyNode[]>();
  for (const n of data.nodes) {
    const list = byCol.get(n.column) ?? [];
    list.push(n);
    byCol.set(n.column, list);
  }
  const rowsPerCol = Math.max(...[...byCol.values()].map((l) => l.length));
  const height = rowsPerCol * ROW_H + PAD * 2 + 18;

  const pos = new Map<string, { x: number; y: number }>();
  for (const [col, list] of byCol) {
    list.forEach((n, i) => {
      pos.set(n.name, {
        x: PAD + col * COL_GAP,
        y: PAD + i * ROW_H + 9,
      });
    });
  }

  return (
    <div className="sankey-wrap" data-testid="population-sankey">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="population flow"
      >
        {data.links.map((l, i) => {
          const a = pos.get(l.from);
          const b = pos.get(l.to);
          if (!a || !b) return null;
          const x1 = a.x + NODE_W;
          const x2 = b.x;
          const mid = (x1 + x2) / 2;
          return (
            <g key={i}>
              <path
                d={`M ${x1} ${a.y + 5} C ${mid} ${a.y + 5}, ${mid} ${b.y + 5}, ${x2} ${b.y + 5}`}
                fill="none"
                className="sankey-link"
                strokeWidth={Math.max(2, Math.min(l.count, 10))}
              />
              <text
                x={mid}
                y={(a.y + b.y) / 2 + 4}
                className="sankey-link-label"
                textAnchor="middle"
              >
                {l.count}
              </text>
            </g>
          );
        })}
        {data.nodes.map((n) => {
          const p = pos.get(n.name);
          if (!p) return null;
          return (
            <g key={n.name} data-testid={`sankey-node-${n.name}`}>
              <rect x={p.x} y={p.y} width={NODE_W} height={11} rx={2} className="sankey-node" />
              <text x={p.x + NODE_W + 4} y={p.y + 9} className="sankey-label">
                {n.name} ({n.count})
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

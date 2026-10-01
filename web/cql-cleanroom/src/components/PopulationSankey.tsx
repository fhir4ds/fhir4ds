
/**
 * Vertical attrition chart (Attrition pane, MR tab).
 *
 * One row per population in FHIR CQM order: label left, horizontal bar
 * right (width ∝ count / max). Exclusion-ish populations (denominator
 * exclusion/exception, numerator exclusion) render INDENTED under their
 * gating population to show the attrition hierarchy. Rows are
 * collapsible per top-level population.
 *
 * Data comes from evaluation rows over boolean population columns.
 * Rendered as pure SVG — no chart lib. Testids: population-sankey
 * container + sankey-node-{name} per row (legacy names kept).
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

/** FHIR CQM order (same ranking the Sankey used). */
const ORDERED_PREFIXES = [
  "IPP",
  "DENOM",
  "DENEX",
  "NUMEX",
  "NUMER",
  "DEXCEP",
];

/** Populations drawn indented (exclusions/exceptions under their gate). */
const NESTED = new Set([
  "denominator_exclusion",
  "denominator_exception",
  "numerator_exclusion",
]);

function orderedColumnIndex(name: string): number {
  const up = name.toUpperCase();
  for (let i = 0; i < ORDERED_PREFIXES.length; i++) {
    if (up.startsWith(ORDERED_PREFIXES[i])) return i;
  }
  return ORDERED_PREFIXES.length;
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

const LABEL_W = 150;
const BAR_MAX = 180;
const ROW_H = 30;
const BAR_H = 14;
const PAD = 8;
const INDENT = 20;

export function PopulationSankey({ data }: { data: SankeyData }) {
  const visible = data.nodes;
  const max = Math.max(...data.nodes.map((n) => n.count), 1);
  const width = LABEL_W + BAR_MAX + PAD * 3;
  const height = visible.length * ROW_H + PAD * 2;

  return (
    <div className="sankey-wrap" data-testid="population-sankey">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="population attrition"
      >
        {visible.map((n, i) => {
          const nested = NESTED.has(n.name);
          const y = PAD + i * ROW_H;
          const barW = Math.round((n.count / max) * BAR_MAX);
          const label = n.name.replace(/_/g, " ");
          return (
            <g key={n.name} data-testid={`sankey-node-${n.name}`}>
              <text
                x={nested ? LABEL_W - INDENT : PAD}
                y={y + BAR_H - 3}
                className="sankey-label"
                textAnchor={nested ? "end" : "start"}
              >
                {nested ? "└ " : ""}
                {label} ({n.count})
              </text>
              <rect
                x={nested ? LABEL_W + INDENT : LABEL_W}
                y={y}
                width={Math.max(barW, n.count > 0 ? 3 : 1)}
                height={BAR_H}
                rx={2}
                className={`sankey-bar${nested ? " nested" : ""}`}
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

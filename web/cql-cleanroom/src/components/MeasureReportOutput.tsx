import { useMemo } from "react";
import type { EvaluateResult } from "../lib/protocol";
import { PaginatedTable } from "./PaginatedTable";
import {
  cellDiffClass,
  diffPopKey,
  diffRuns,
  type Artifact,
} from "../lib/runDiff";
import { PopulationSankey } from "./PopulationSankey";

/**
 * REORG phase 6b: the Measure Report OUTPUT — pivot of the materialized
 * per-patient MeasureReports plus the population attrition Sankey —
 * rendered inside the CQL console's "mr" panel while a measure editor
 * tab is active (the col2 stacked pane is gone).
 */

export function useRunDiff(
  result: EvaluateResult | null,
  baselineArtifact: Artifact | null,
) {
  const currentArtifact: Artifact | null = result
    ? Object.fromEntries(
        result.rows.map((r) => {
          const pid = String(r.patient_id ?? "");
          const pops: Record<string, boolean | null> = {};
          for (const c of result.columns) {
            if (c === "patient_id") continue;
            const v = r[c];
            pops[c] = v === true ? true : v === false ? false : null;
          }
          return [pid, pops];
        }),
      )
    : null;
  return useMemo(
    () => diffRuns(currentArtifact, baselineArtifact),
    [currentArtifact, baselineArtifact],
  );
}

export function MrOutput({
  result,
  reports,
  measure,
  runDiff,
}: {
  result: EvaluateResult | null;
  reports: Array<Record<string, unknown>> | null;
  measure: Record<string, unknown> | null;
  runDiff: ReturnType<typeof diffRuns>;
}) {
  const populationColumns = (result?.columns ?? []).filter(
    (c) => c !== "patient_id",
  );
  return (
    <>
      {reports && reports.length > 0 ? (
        <div className="pane output-pane" data-testid="mr-reports">
          <header className="pane-header">
            <h3>Output</h3>
          </header>
          <MrPivotTable reports={reports} runDiff={runDiff} />
        </div>
      ) : (
        <p className="pane-hint" data-testid="mr-empty">
          {measure
            ? "Run an evaluation to materialize MeasureReports."
            : "Configure the Measure mapping, then re-evaluate."}
        </p>
      )}
      {result && populationColumns.length > 0 && (
        <div className="pane output-pane" data-testid="attrition-pane">
          <header className="pane-header">
            <h3>Attrition</h3>
          </header>
          <SankeyFromRows columns={populationColumns} rows={result.rows} />
        </div>
      )}
    </>
  );
}

/**
 * Pivot the per-patient MeasureReports: one row per patient, one column
 * per population (matching the CQL results table shape). A group_id
 * column appears only when any report carries more than one group.
 */
function MrPivotTable({
  reports,
  runDiff,
}: {
  reports: Array<Record<string, unknown>>;
  runDiff: ReturnType<typeof diffRuns>;
}) {
  const multiGroup = reports.some(
    (r) => ((r.group as Array<unknown>) ?? []).length > 1,
  );
  const codes: string[] = [];
  const cells = new Map<
    string,
    { patient: string; gid: string; counts: Map<string, string> }
  >();
  for (const r of reports) {
    const subject =
      (r.subject as { reference?: string } | undefined)?.reference ?? "—";
    for (const g of (r.group as Array<Record<string, unknown>>) ?? []) {
      const gid = String(g.id ?? "");
      for (const p of (g.population as Array<Record<string, unknown>>) ?? []) {
        const code =
          ((p.code as { coding?: Array<{ code?: string }> })?.coding ?? [])[0]
            ?.code ?? "—";
        const col = multiGroup ? `${gid}:${code}` : code;
        if (!codes.includes(col)) codes.push(col);
        const key = subject;
        const entry = cells.get(key) ?? {
          patient: subject,
          gid,
          counts: new Map<string, string>(),
        };
        entry.counts.set(col, String(p.count ?? "—"));
        cells.set(key, entry);
      }
    }
  }
  const sortedPatients = [...cells.keys()].sort();
  const groups =
    (reports[0] && (reports[0].group as Array<unknown>)?.length) ?? 0;
  return (
    <PaginatedTable
      testId="mr-table"
      rowCount={sortedPatients.length}
      stats={
        <>
          {reports.length} reports
          {groups > 1 ? ` · ${groups} groups` : ""}
        </>
      }
      header={
        <tr>
          <th>patient</th>
          {multiGroup && <th>group</th>}
          {codes.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      }
      renderRows={({ slice }) =>
        slice(sortedPatients).map((pid) => {
          const row = cells.get(pid)!;
          const barePid = pid.replace(/^Patient\//, "");
          return (
            <tr key={pid} data-testid={`mr-row-${pid}`}>
              <td>{row.patient}</td>
              {multiGroup && <td>{row.gid}</td>}
              {codes.map((c) => {
                const pop = c.includes(":") ? c.split(":")[1] : c;
                const dcls = cellDiffClass(runDiff, barePid, diffPopKey(pop));
                return (
                  <td key={c} className={dcls ?? undefined}>
                    {row.counts.get(c) ?? "—"}
                  </td>
                );
              })}
            </tr>
          );
        })
      }
    />
  );
}

/** Sankey built inline from evaluation rows. */
function SankeyFromRows({
  columns,
  rows,
}: {
  columns: string[];
  rows: Array<Record<string, unknown>>;
}) {
  return (
    <PopulationSankey
      data={{
        nodes: columns.map((name, i) => ({
          column: i,
          name,
          count: rows.filter((r) => r[name] === true).length,
        })),
        links: (() => {
          const links: Array<{ from: string; to: string; count: number }> = [];
          for (let i = 0; i < columns.length; i++) {
            for (let j = i + 1; j < columns.length; j++) {
              const a = columns[i];
              const b = columns[j];
              const both = rows.filter(
                (r) => r[a] === true && r[b] === true,
              ).length;
              if (both > 0) links.push({ from: a, to: b, count: both });
            }
          }
          return links;
        })(),
      }}
    />
  );
}

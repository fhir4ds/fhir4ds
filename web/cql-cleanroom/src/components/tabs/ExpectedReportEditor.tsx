import { useMemo } from "react";

/**
 * WORKBENCH_REORG phase 3 — authored-expected-results editor tab.
 * Edits ONE MeasureReport resource (the expected populations for a
 * patient): subject reference + per-group population counts. The same
 * resource shape the nav's Expected drawer lists and measureBundle's
 * rows_from_measure_reports consumes.
 */

type Mr = Record<string, unknown>;

interface PopCoding {
  code?: { coding?: Array<{ code?: string }> };
  count?: number;
}
interface PopGroup {
  population?: PopCoding[];
}

function popCode(p: PopCoding): string {
  return p.code?.coding?.[0]?.code ?? "?";
}

export function ExpectedReportEditor({
  report,
  onChange,
}: {
  report: Mr;
  onChange: (next: Mr) => void;
}) {
  const groups = useMemo(
    () => (Array.isArray(report.group) ? (report.group as PopGroup[]) : []),
    [report],
  );
  const subject =
    typeof (report.subject as { reference?: unknown })?.reference === "string"
      ? ((report.subject as { reference: string }).reference)
      : "";

  const setSubject = (ref: string) =>
    onChange({ ...report, subject: { reference: ref } });

  const patchCount = (gi: number, pi: number, count: number) => {
    const nextGroups = groups.map((g, i) =>
      i !== gi
        ? g
        : {
            ...g,
            population: (g.population ?? []).map((p, j) =>
              j !== pi ? p : { ...p, count },
            ),
          },
    );
    onChange({ ...report, group: nextGroups });
  };

  const addPopulation = (gi: number) => {
    const nextGroups = groups.map((g, i) =>
      i !== gi
        ? g
        : {
            ...g,
            population: [
              ...(g.population ?? []),
              { code: { coding: [{ code: "initial-population" }] }, count: 0 },
            ],
          },
    );
    onChange({ ...report, group: nextGroups });
  };

  const removePopulation = (gi: number, pi: number) => {
    const nextGroups = groups.map((g, i) =>
      i !== gi
        ? g
        : { ...g, population: (g.population ?? []).filter((_, j) => j !== pi) },
    );
    onChange({ ...report, group: nextGroups });
  };

  const setPopCode = (gi: number, pi: number, code: string) => {
    const nextGroups = groups.map((g, i) =>
      i !== gi
        ? g
        : {
            ...g,
            population: (g.population ?? []).map((p, j) =>
              j !== pi
                ? p
                : { ...p, code: { coding: [{ code }] } },
            ),
          },
    );
    onChange({ ...report, group: nextGroups });
  };

  return (
    <section className="pane" data-testid="expected-report-editor">
      <div className="pane-header">
        <h2>Expected result — {subject || "(no subject)"}</h2>
        <span className="pane-meta">MeasureReport</span>
      </div>
      <div className="drawer-body">
        <label className="er-subject-row">
          subject{" "}
          <input
            data-testid="expected-subject"
            value={subject}
            placeholder="Patient/p1"
            onChange={(e) => setSubject(e.target.value)}
          />
        </label>
        {groups.length === 0 && (
          <p className="pane-hint">No groups. Use raw JSON to add one.</p>
        )}
        {groups.map((g, gi) => (
          <div className="er-group" key={gi}>
            <div className="er-group-title">group {gi + 1}</div>
            {(g.population ?? []).map((p, pi) => (
              <div className="er-pop-row" key={pi}>
                <input
                  className="er-pop-code"
                  aria-label="population code"
                  value={popCode(p)}
                  onChange={(e) => setPopCode(gi, pi, e.target.value)}
                />
                <input
                  className="er-pop-count"
                  data-testid={`expected-count-${popCode(p)}`}
                  type="number"
                  min={0}
                  max={1}
                  aria-label="count"
                  value={p.count ?? 0}
                  onChange={(e) =>
                    patchCount(gi, pi, Math.max(0, Number(e.target.value) || 0))
                  }
                />
                <button
                  className="vs-code-del"
                  title="remove population"
                  onClick={() => removePopulation(gi, pi)}
                >
                  ×
                </button>
              </div>
            ))}
            <button
              className="er-pop-add"
              onClick={() => addPopulation(gi)}
            >
              + population
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

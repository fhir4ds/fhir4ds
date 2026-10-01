import { test } from "@playwright/test";
import { readFileSync } from "node:fs";

/**
 * C1-U8 matrix leg 3: run_tests on the §3.8 shared fixture through the
 * app's worker bridge; print the envelope between markers for the
 * Python three-way matrix test (operations/tests/test_capability_matrix.py).
 *
 * C2-U4 compare leg: when the fixture carries a `compare` section
 * (baseline/current evidence payloads), ALSO run compare_evidence and
 * print it between COMPARE markers (one fixture mechanism — S-C2-5).
 *
 * The fixture JSON (library/resources/cases/output_columns[/compare])
 * is written by the Python side; its path arrives via
 * CLEANROOM_MATRIX_FIXTURE.
 */

const FIXTURE_PATH =
  process.env.CLEANROOM_MATRIX_FIXTURE ?? "/tmp/cleanroom_matrix_fixture.json";

interface MatrixFixture {
  library: { name: string; text: string };
  resources: Array<Record<string, unknown>>;
  cases: { schema: number; cases: Array<Record<string, unknown>> };
  output_columns: Record<string, string>;
  compare?: {
    baseline: Record<string, unknown>;
    current: Record<string, unknown>;
    output_columns?: Record<string, string> | null;
  };
  measure?: {
    mapping: Array<{ define: string; code: string }>;
    expected_rows?: Array<Record<string, unknown>>;
  };
}

test("cleanroom matrix leg run_tests", async ({ page }, testInfo) => {
  // Standalone runs (no fixture injected by the Python three-way test)
  // have nothing to assert — skip cleanly instead of failing on a stale
  // /tmp default. The Python leg always sets CLEANROOM_MATRIX_FIXTURE.
  if (!process.env.CLEANROOM_MATRIX_FIXTURE) {
    testInfo.skip(true, "CLEANROOM_MATRIX_FIXTURE not set (Python matrix test injects it)");
    return;
  }
  const fixture: MatrixFixture = JSON.parse(
    readFileSync(FIXTURE_PATH, "utf-8"),
  );

  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() =>
    Boolean((window as any).__cleanroom),
  );

  const envelope = await page.evaluate(async (fx: MatrixFixture) => {
    const resp = await (window as any).__cleanroom({
      type: "run_tests",
      libraries: [fx.library],
      main: fx.library,
      dataset: { resources: fx.resources },
      tests: fx.cases,
      output_columns: fx.output_columns,
    });
    return resp.envelope as string;
  }, fixture);

  // Machine-readable handoff to the Python matrix test.
  console.log(`CLEANROOM_ENVELOPE_BEGIN${envelope}CLEANROOM_ENVELOPE_END`);

  // C2-U4: compare leg on the same fixture (section optional).
  if (fixture.compare) {
    const delta = await page.evaluate(async (cmp: NonNullable<MatrixFixture["compare"]>) => {
      const resp = await (window as any).__cleanroom({
        type: "compare_evidence",
        baseline: cmp.baseline,
        current: cmp.current,
        output_columns: cmp.output_columns ?? null,
      });
      return resp.envelope as string;
    }, fixture.compare);
    console.log(`CLEANROOM_COMPARE_BEGIN${delta}CLEANROOM_COMPARE_END`);
  }

  // Measure-reports campaign: composed round-trip through the worker —
  // measure_from_definitions -> evaluate (Measure-derived columns) ->
  // measure_report_from_rows -> rows_from_measure_reports.
  if (fixture.measure) {
    const rowsEnv = await page.evaluate(async (fx: MatrixFixture) => {
      const mapping = fx.measure!.mapping;
      const mResp = await (window as any).__cleanroom({
        type: "measure_from_definitions",
        libraries: [fx.library],
        main: fx.library,
        mapping,
      });
      const mEnv = JSON.parse(mResp.envelope);
      if (!mEnv.ok) return JSON.stringify(mEnv);
      // Measure -> output columns (snake_case codes), same derivation
      // as the app (App.tsx outputColumnsFromMeasure).
      const outCols: Record<string, string> = {};
      for (const g of mEnv.measure.group ?? []) {
        for (const pop of g.population ?? []) {
          const code = pop.code?.coding?.[0]?.code;
          const define = pop.criteria?.expression;
          if (code && define) outCols[code.replace(/-/g, "_")] = define;
        }
      }
      const evResp = await (window as any).__cleanroom({
        type: "evaluate_library",
        libraries: [fx.library],
        main: fx.library,
        dataset: { resources: fx.resources },
        output_columns: outCols,
      });
      const evEnv = JSON.parse(evResp.envelope);
      if (!evEnv.ok) return JSON.stringify(evEnv);
      const repResp = await (window as any).__cleanroom({
        type: "measure_report_from_rows",
        measure: mEnv.measure,
        rows: evEnv.rows,
        columns: evEnv.columns,
      });
      const repEnv = JSON.parse(repResp.envelope);
      if (!repEnv.ok) return JSON.stringify(repEnv);
      const backResp = await (window as any).__cleanroom({
        type: "rows_from_measure_reports",
        reports: repEnv.reports,
        population_codes: mapping.map((m) => m.code),
      });
      return (backResp as { envelope: string }).envelope as string;
    }, fixture);
    console.log(`CLEANROOM_MEASURE_BEGIN${rowsEnv}CLEANROOM_MEASURE_END`);
  }
});

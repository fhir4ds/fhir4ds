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
});

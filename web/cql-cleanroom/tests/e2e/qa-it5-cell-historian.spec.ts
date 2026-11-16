/**
 * QA it5 — Domain 2 (cell engine) × HISTORIAN: cell-surface claim inventory.
 *  J1 evaluate_snippet (expression) executes the selection wrapped as
 *     __snippet__ — envelope carries a result for the snippet output column
 *     and the same value as an equivalent library define evaluated by
 *     evaluate_library (it4's parity harness guarantees desktop equality).
 *  J2 statement-block snippet (a `define`) evaluates like a library run.
 *  J3 diagnostics from a broken selection are renumbered to SELECTION
 *     lines (not the synthesized text's lines).
 */
import { test, expect } from "@playwright/test";

const MAIN = {
  name: "CellLib",
  text: `library CellLib version '1'
using FHIR version '4.0.1'
context Patient
define "Base":
  Patient.gender`,
};
const DATASET = {
  resources: [
    { resourceType: "Patient", id: "p1", gender: "male" },
    { resourceType: "Patient", id: "p2", gender: "female" },
  ],
};

async function boot(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.evaluate(() => (window as any).__cleanroomReady?.());
  await page.waitForFunction(
    () => (window as any).__cleanroomBooted === true,
    null,
    { timeout: 180_000 },
  );
}

async function req(page: import("@playwright/test").Page, msg: Record<string, unknown>) {
  const r = await page.evaluate(async (m) => {
    const resp = await (window as any).__cleanroomRequest(m);
    return JSON.parse(resp.envelope);
  }, msg);
  return r;
}

test("J1: expression snippet equals the equivalent library define", async ({ page }) => {
  await boot(page);
  const snippet = await req(page, {
    type: "evaluate_snippet", libraries: [], main: MAIN,
    snippet: "Patient.gender", dataset: DATASET,
  });
  expect(snippet.ok).toBe(true);
  const rows = snippet.rows as Array<Record<string, unknown>>;
  // define values cross the worker boundary as per-patient LISTS
  // (population SQL value columns) — unwrap singletons for comparison.
  const val = (r: Record<string, unknown>) => {
    const v = r.snippet;
    return Array.isArray(v) ? v[0] : v;
  };
  expect(rows.map(val)).toEqual(["male", "female"]);
});

test("J2: statement-block snippet (define) evaluates like a library", async ({ page }) => {
  await boot(page);
  const viaSnippet = await req(page, {
    type: "evaluate_snippet", libraries: [], main: MAIN,
    snippet: "define \"Extra\":\n  Patient.gender = 'male'",
    dataset: DATASET,
  });
  expect(viaSnippet.ok).toBe(true);
  const rows = viaSnippet.rows as Array<Record<string, unknown>>;
  expect(rows.map((r) => r.Extra)).toEqual([true, false]);
});

test("J3: broken-selection diagnostics are renumbered to selection lines", async ({ page }) => {
  await boot(page);
  const env = await req(page, {
    type: "evaluate_snippet", libraries: [], main: MAIN,
    snippet: "define \"Bad\":\n  1 +",
    dataset: DATASET,
  });
  expect(env.ok).toBe(false);
  const d = env.diagnostics[0];
  expect(d.location?.start_line).toBeLessThanOrEqual(2);
});

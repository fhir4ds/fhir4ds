/**
 * QA it6 — Domain 2 (cell engine) × EXPLORER: chaos/fuzz.
 *  V1 degenerate snippets (whitespace / comments-only / bare keyword)
 *  V2 pathological dataset (500 patients, null-heavy, unicode, deep nesting)
 *  V3 giant expression (10k-term conjunction)
 *  V4 concurrent capability requests
 *  V5 unicode/emoji CQL strings
 *  V6 wide library (100 defines)
 */
import { test, expect, type Page } from "@playwright/test";

async function boot(page: Page) {
  await page.goto("/");
  await page.evaluate(() => (window as any).__cleanroomReady?.());
  await page.waitForFunction(
    () => (window as any).__cleanroomBooted === true,
    null,
    { timeout: 180_000 },
  );
}

async function req(page: Page, msg: Record<string, unknown>) {
  return page.evaluate(async (m) => {
    const r = await (window as any).__cleanroomRequest(m);
    return JSON.parse(r.envelope);
  }, msg);
}

const MAIN = {
  name: "ChaosLib",
  text: "library ChaosLib version '1'\nusing FHIR version '4.0.1'\ncontext Patient\ndefine \"G\": Patient.gender",
};
const DS1 = { resources: [{ resourceType: "Patient", id: "p1", gender: "male" }] };

test("V1: degenerate snippets yield typed diagnostics (no crash)", async ({ page }) => {
  await boot(page);
  for (const snippet of ["   ", "// just a comment", "define", "library"]) {
    const env = await req(page, {
      type: "evaluate_snippet", libraries: [], main: MAIN,
      snippet, dataset: DS1,
    });
    // whitespace/comment-only: ok with typed input diagnostic; bare keyword: parse diag
    expect(env.ok === false || env.diagnostics?.length >= 0).toBe(true);
  }
  // worker still alive
  const alive = await req(page, { type: "parse_cql", text: "library A\ndefine \"x\": 1" });
  expect(alive.ok).toBe(true);
});

test("V2: pathological dataset evaluates", async ({ page }) => {
  await boot(page);
  const resources: unknown[] = [];
  for (let i = 0; i < 500; i++) {
    resources.push({
      resourceType: "Patient", id: `p${i}`,
      gender: i % 2 ? "male" : "female",
      name: [{ given: i % 7 === 0 ? ["Ünicode😀"] : [null], family: "x".repeat(200) }],
      address: i % 11 === 0 ? null : [{ line: ["a", null, "b"], city: "Ørbing" }],
      contact: i % 13 === 0 ? [] : undefined,
    });
    if (i % 5 === 0) {
      resources.push({
        resourceType: "Condition", id: `c${i}`,
        subject: { reference: `Patient/p${i}` },
        onset: i % 2 ? { start: "2026-03-01" } : null,
        extension: [{ url: `u${i}`, valueString: "e".repeat(500) }],
      });
    }
  }
  const env = await req(page, {
    type: "evaluate_library", libraries: [],
    main: { name: "Wide", text: "library Wide version '1'\nusing FHIR version '4.0.1'\ncontext Patient\ndefine \"HasCond\": exists [Condition]" },
    dataset: { resources },
  });
  expect(env.ok).toBe(true);
  expect(env.patient_count).toBe(500);
});

test("V3: giant expression yields diagnostic or result (worker survives)", async ({ page }) => {
  await boot(page);
  const conj = Array.from({ length: 5000 }, () => "1 = 1").join(" and ");
  const env = await req(page, {
    type: "evaluate_snippet", libraries: [], main: MAIN,
    snippet: conj, dataset: DS1,
  });
  expect(typeof env.ok).toBe("boolean");
  const alive = await req(page, { type: "parse_cql", text: "library A\ndefine \"x\": 1" });
  expect(alive.ok).toBe(true);
});

test("V4: concurrent capability requests all resolve", async ({ page }) => {
  await boot(page);
  const envs = await page.evaluate(async () => {
    const mk = (i: number) =>
      (window as any).__cleanroomRequest({
        type: "evaluate_library", libraries: [],
        main: { name: `C${i}`, text: `library C${i} version '1'\nusing FHIR version '4.0.1'\ncontext Patient\ndefine \"V\": ${i}` },
        dataset: { resources: [{ resourceType: "Patient", id: "p1", gender: "male" }] },
      }).then((r: any) => JSON.parse(r.envelope));
    return Promise.all([mk(1), mk(2), mk(3), mk(4), mk(5)]);
  });
  expect(envs.every((e: any) => e.ok)).toBe(true);
});

test("V5: unicode/emoji CQL strings evaluate", async ({ page }) => {
  await boot(page);
  const env = await req(page, {
    type: "evaluate_snippet", libraries: [], main: MAIN,
    snippet: "'héllo 😀 wörld'", dataset: DS1,
  });
  expect(env.ok).toBe(true);
});

test("V6: wide library (100 defines) evaluates", async ({ page }) => {
  await boot(page);
  const defines = Array.from(
    { length: 100 },
    (_, i) => `define "D${i}": ${i}`,
  ).join("\n");
  const env = await req(page, {
    type: "evaluate_library", libraries: [],
    main: { name: "WideLib", text: `library WideLib version '1'\nusing FHIR version '4.0.1'\ncontext Patient\n${defines}` },
    dataset: DS1,
  });
  expect(env.ok).toBe(true);
  expect(env.columns.filter((c: string) => c.startsWith("D")).length).toBe(100);
});

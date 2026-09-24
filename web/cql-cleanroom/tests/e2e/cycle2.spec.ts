import { test } from "@playwright/test";

/**
 * C2-U2 e2e: parse include_ast (AstPane) + compare_evidence through the
 * worker bridge on the built bundle.
 */

test.describe("cleanroom cycle-2 capabilities", () => {
  test("ast pane renders statement trees", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    await page.waitForFunction(() => Boolean((window as any).__cleanroom));

    const ast = await page.evaluate(async () => {
      const r = await (window as any).__cleanroom({
        type: "parse_cql",
        text: `library AstDemo version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
define "D1":
  1 + 2
`,
        include_ast: true,
      });
      return JSON.parse(r.envelope);
    });
    if (!ast.ok) console.log("AST RESP:", JSON.stringify(ast).slice(0, 400));
    if (ast.ok) {
      console.log("AST_KIND:", ast.ast.statements.D1.kind);
      console.log("AST_OP:", ast.ast.statements.D1.children.operator);
    }

    // UI: AST now lives in Results — run an evaluation, then Show AST.
    await page.click("[data-testid=run-eval]");
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });
    await page.click('[data-testid=show-ast]');
    await page.click('[data-testid=ast-load]');
    await page.waitForSelector('[data-testid^=ast-def-]', { timeout: 30_000 });
    const defName = await page
      .locator('[data-testid^=ast-def-]')
      .first()
      .textContent();
    console.log("AST_DEF:", defName);
  });

  test("compare_evidence delta through the worker", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".version-badge", { timeout: 150_000 });
    await page.waitForFunction(() => Boolean((window as any).__cleanroom));

    const resp = await page.evaluate(async () => {
      const r = await (window as any).__cleanroom({
        type: "compare_evidence",
        baseline: {
          patients: { p1: { populations: { initial_population: true } }, p2: { populations: { initial_population: false } } },
        },
        current: {
          patients: { p1: { populations: { initial_population: false } }, p3: { populations: { initial_population: true } } },
        },
      });
      return JSON.parse(r.envelope);
    });
    console.log("COMPARE_CHANGED:", resp.changed);
    console.log("COMPARE_SUMMARY:", JSON.stringify(resp.summary));
    console.log(
      "COMPARE_ROWS:",
      JSON.stringify(resp.patients.map((p: any) => `${p.patient_id}:${p.column}:${p.classification}`)),
    );
  });
});

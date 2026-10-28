import { test } from "@playwright/test";
import { bootTextReady } from "./bootText";

/**
 * C2-U2 e2e: parse include_ast (AstPane) + compare_evidence through the
 * worker bridge on the built bundle.
 */

test.describe("cleanroom cycle-2 capabilities", () => {
  test("ast pane renders statement trees", async ({ page }) => {
    await bootTextReady(page);
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
    // S25: the showcase boot doesn't auto-evaluate; reset to the demo
    // (p1/p2/p3 auto-eval) first.
    await page.click("[data-testid=file-menu]");
    await page.click("[data-testid=workspace-reset]");
    await page.waitForTimeout(800);
    await page.waitForSelector("[data-testid=results-table]", {
      timeout: 60_000,
    });
    // WORKBENCH_REORG phase 5: AST is a console sub-tab now.
    // REORG 6h: no Refresh button — the tree auto-parses on tab open.
    await page.click('[data-testid=console-tab-ast]');
    await page.waitForSelector('[data-testid^=ast-def-]', { timeout: 30_000 });
    const defName = await page
      .locator('[data-testid^=ast-def-]')
      .first()
      .textContent();
    console.log("AST_DEF:", defName);
  });

  test("compare_evidence delta through the worker", async ({ page }) => {
    await bootTextReady(page);
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

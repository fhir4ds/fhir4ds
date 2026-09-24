import { test } from "@playwright/test";

/**
 * C3-U6 e2e: visual editor emits valid CQL and applies it to the active
 * library tab (explicit apply; round-trip parse guard).
 */
test("visual editor: emit → apply → library parses", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector(".version-badge", { timeout: 150_000 });
  await page.waitForFunction(() => Boolean((window as any).__cleanroom));

  // Visual editor is now an editor-column drawer — open it first.
  await page.click('[data-testid=drawer-graph-toggle]');

  // Emit from the default graph (Retrieve Patient → Exists → Output)
  await page.click('[data-testid=graph-emit]');
  const preview = await page.textContent('[data-testid=graph-preview]');
  console.log("EMIT_CONTAINS:", String(preview).includes("exists [Patient]"));

  // Apply → the editor text becomes the emitted library
  await page.click('[data-testid=graph-apply]');
  await page.waitForSelector('[data-testid=graph-applied]', { timeout: 30_000 });

  // The active library tab now parses (editor pane shows parsed ✓)
  await page.waitForFunction(
    () => {
      const el = document.querySelector('[data-testid=parse-status]');
      return el && /parsed\s*✓/.test(el.textContent ?? "");
    },
    undefined,
    { timeout: 60_000 },
  );
  const status = await page.textContent('[data-testid=parse-status]');
  console.log("PARSE_STATUS:", status);
});
